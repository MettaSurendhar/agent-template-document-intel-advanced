import json

import boto3

from api import args
from api.schemas.agents import Citation
from api.schemas.llm import GenerateResponse


class AmazonBedrockClient:
    """Wrapper around the Amazon Bedrock client."""

    def __init__(self) -> None:
        self.knowledge_base_id = args.knowledge_base_id
        self.model_id = args.model_id
        self.bedrock_agent_runtime = boto3.client(
            "bedrock-agent-runtime",
            region_name=args.aws_region,
        )
        # For Knowledge Bases.
        self.bedrock_runtime = boto3.client(
            "bedrock-runtime",
            region_name=args.aws_region,
        )
        self.s3_client = boto3.client(
            "s3",
            region_name=args.aws_region,
        )

    def retrieve(self, prompt: str, s3_uri_filters: list[str] | None = None) -> tuple[list[str], list[Citation]]:
        """Retrieve chunks from the RAG source, i.e., Amazon Bedrock Knowledge Bases.

        Optionally filter results by one or more S3 URIs of the ingested documents.
        """
        vector_config: dict = {"numberOfResults": 10}

        if s3_uri_filters:
            if len(s3_uri_filters) == 1:
                vector_config["filter"] = {
                    "equals": {
                        "key": "x-amz-bedrock-kb-source-uri",
                        "value": s3_uri_filters[0],
                    }
                }
            else:
                vector_config["filter"] = {
                    "orAll": [
                        {
                            "equals": {
                                "key": "x-amz-bedrock-kb-source-uri",
                                "value": uri,
                            }
                        }
                        for uri in s3_uri_filters
                    ]
                }

        response = self.bedrock_agent_runtime.retrieve(
            knowledgeBaseId=self.knowledge_base_id,
            retrievalQuery={"text": prompt},
            retrievalConfiguration={"vectorSearchConfiguration": vector_config},
        )

        retrieval_results = [
            r
            for r in response.get("retrievalResults", [])
            if r.get("score", 0.0) > 0.4 and r.get("content", {}).get("type") == "TEXT"
        ]

        chunks = []
        citations_raw = []

        for r in retrieval_results:
            text = r["content"].get("text")
            if not text:
                continue

            chunks.append(text)

            uri = r.get("metadata", {}).get("x-amz-bedrock-kb-source-uri")
            page = r.get("metadata", {}).get("x-amz-bedrock-kb-document-page-number", -1)

            if uri:
                citations_raw.append({"uri": uri, "title": uri.split("/")[-1], "page": int(page)})

        unique_citations_dict = {c["uri"]: c for c in citations_raw}
        unique_citations = [Citation(title=c["title"], uri=c["uri"]) for c in unique_citations_dict.values()]

        return chunks, unique_citations

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        chunks: list[str] | None = None,
        citations: list[Citation] | None = None,
    ) -> str:
        """Generate an LLM response for a prompt with optional context chunks."""
        if system_prompt is None:
            system_prompt = (
                "You are a deterministic, context-bound assistant.\n\n"
                "CONSTRAINTS:\n"
                "1. Use ONLY the information explicitly provided in the context.\n"
                "2. Perform arithmetic calculations ONLY if all required inputs exist in the context.\n"
                "3. Do NOT use external knowledge.\n"
                "4. Do NOT infer, assume, reinterpret, or expand beyond the provided context.\n\n"
                "OUTPUT FORMAT (STRICT REQUIREMENT):\n"
                "- You MUST return ONLY a valid JSON string.\n"
                "- Do NOT include markdown, explanations, commentary, or extra text.\n"
                "- Do NOT wrap the JSON in code fences.\n"
                "- The response must start with '{' and end with '}'.\n\n"
                "RULES:\n"
                "- The JSON must contain EXACTLY two keys: 'answer' and 'reason'.\n"
                "- No additional keys are allowed.\n"
                "- All values must be strings.\n"
                "- No trailing commas.\n\n"
                "WHEN THE ANSWER EXISTS IN CONTEXT:\n"
                "- If the answer contains multiple points, place each point on a separate line.\n"
                "- Preserve newline characters in the 'answer' value when formatting multiple points.\n"
                "- 'answer' → contain ONLY the final answer.\n"
                "- 'reason' → must be an empty string ''.\n\n"
                "WHEN THE ANSWER CANNOT BE DERIVED FROM CONTEXT:\n"
                "- 'answer' → must be exactly '__NO_CONTEXT__'\n"
                "- 'reason' → must clearly explain why the answer cannot be derived from the provided context.\n\n"
                "NON-COMPLIANCE IS NOT ALLOWED.\n"
                "Return only the JSON object."
            )

        if chunks:
            max_chunks = 5

            unique_docs = {c.uri for c in (citations or [])}

            if len(unique_docs) > 1:
                max_chunks = 20

            context_text = "\n\n".join(chunks[:max_chunks])
            user_prompt = (
                f"User query: {prompt}\n\nContext (from {len(unique_docs)} documents):\n{context_text}"
                f"\n\nJSON Schema: {json.dumps(GenerateResponse.generate_schema, indent=2)}"
            )
        else:
            user_prompt = prompt

        response = self.bedrock_runtime.converse(
            modelId=self.model_id,
            messages=[{"role": "user", "content": [{"text": user_prompt}]}],
            system=[{"text": system_prompt}],
        )

        response_text = response["output"]["message"]["content"][0]["text"].strip()

        return response_text

    def suggest_questions(self, user_query: str, chunks: list[str], count: int = 5) -> list[str]:
        """
        Generate suggested follow-up questions directly from the retrieved document chunks.

        This avoids multiple KD lookups and improves speed.
        """
        if not chunks:
            return []

        context = "\n\n".join(chunks[:5])

        system_prompt = (
            "You are a helpful assistant. Using only the information "
            "and wording present in the given document excerpts, "
            f"generate {count} simple, clear, and user-friendly follow-up questions. "
            "Each question should be phrased naturally as if asked by a user, "
            "but must strictly rely on the document’s content and terminology "
            "so that they can be used to retrieve relevant data again. "
            "Do not include answers or explanations."
            "Return only the questions, one per line. "
            "Do NOT include numbers, bullets, or prefixes."
        )

        user_prompt = (
            f"User's latest query:\n{user_query}\n\n"
            f"Relevant document context:\n{context}\n\n"
            "Generate follow-up questions now."
        )

        response = self.bedrock_runtime.converse(
            modelId=self.model_id,
            messages=[{"role": "user", "content": [{"text": user_prompt}]}],
            system=[{"text": system_prompt}],
            inferenceConfig={"maxTokens": 256, "temperature": 0.5},
        )

        model_output = response["output"]["message"]["content"][0]["text"]
        questions = [
            line.strip(" .-")
            for line in model_output.split("\n")
            if line.strip() and any(char.isalpha() for char in line)
        ]
        return questions[:count]
