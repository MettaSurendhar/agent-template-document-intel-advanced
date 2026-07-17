import logging
import uuid
from datetime import datetime
from pathlib import PurePosixPath

from opensearchpy import OpenSearch

from api import args

logger = logging.getLogger(__name__)


class OpenSearchUtil:
    """Utility class for interacting with OpenSearch."""

    def __init__(self):
        if not args.aos_endpoint:
            raise ValueError("Missing OpenSearch endpoint in args")

        auth = (args.aos_username, args.aos_password) if args.aos_username and args.aos_password else None

        self.client = OpenSearch(
            hosts=[args.aos_endpoint],
            http_auth=auth,
            http_compress=True,
            use_ssl=args.aos_use_ssl,
            verify_certs=args.aos_verify_certs,
            ssl_assert_hostname=False,
            ssl_show_warn=False,
        )

    def insert_document(
        self,
        index: str,
        body: dict,
        doc_id: str | None = None,
        refresh: bool | str = False,
        wait_for_active_shards: str | None = None,
    ):
        """Insert a document into OpenSearch."""
        params = {}

        if isinstance(refresh, bool):
            params["refresh"] = "true" if refresh else "false"
        elif refresh:
            params["refresh"] = refresh

        if wait_for_active_shards:
            params["wait_for_active_shards"] = wait_for_active_shards

        if doc_id:
            return self.client.index(index=index, id=doc_id, body=body, params=params)
        else:
            return self.client.index(index=index, body=body, params=params)

    def update_document(self, index: str, doc_id: str, body: dict):
        """Update a document in OpenSearch."""
        return self.client.update(index=index, id=doc_id, body=body, params={"refresh": "wait_for"})

    def get_team_document_uris(self, team_id: str) -> list[str]:
        """Fetch all S3 URIs of documents that belong to a team."""
        query = {
            "query": {"term": {"team_id": team_id}},
            "_source": ["object_store.converted"],
            "size": 1000,
        }
        results = self.client.search(index=args.aos_documents_index, body=query)
        # return [hit["_source"]["object_store"]["converted"] for hit in results.get("hits", {}).get("hits", [])]

        uris = []
        for hit in results.get("hits", {}).get("hits", []):
            obj_store = hit.get("_source", {}).get("object_store", {})
            if obj_store and obj_store.get("converted"):
                uris.append(obj_store["converted"])
            else:
                logging.info(f"Skipping document missing object_store: {hit.get('_id')}")
        return uris

    def get_user_document_uris(self, user_email: str):
        """Fetch all S3 URIs of documents that belong to a user."""
        query = {
            "query": {"term": {"user_email.keyword": user_email}},
            "_source": ["object_store.converted"],
            "size": 1000,
        }

        results = self.client.search(index=args.aos_private_documents_index, body=query)

        uris = []
        for hit in results.get("hits", {}).get("hits", []):
            obj_store = hit.get("_source", {}).get("object_store", {})
            converted = obj_store.get("converted")
            if converted:
                uris.append(converted)
            else:
                logging.info(f"Skipping document missing object_store.converted: {hit.get('_id')}")

        return uris

    def log_audit_event(
        self,
        user_id: str,
        event_type: str,
        description: str,
        team_id: str | None = None,
        metadata: dict | None = None,
    ):
        """
        Log an audit event into the docintel_audit_logs index.

        event_type: "UPLOAD" | "QUERY"
        metadata: Optional extra data (e.g., message_id, citations, s3_path, tags)
        """
        audit_event = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow(),
            "user_id": user_id,
            "team_id": team_id,
            "event_type": event_type,
            "description": description,
            "metadata": metadata or {},
        }
        return self.insert_document(index=args.aos_audit_index, body=audit_event)

    def get_existing_document_map(self, scope: str, value: str) -> dict[str, str]:
        """
        Fetch existing documents from OpenSearch based on scope (team or user).

        - scope='team' → match team_id
        - scope='user' → match user_email
        Returns a dictionary mapping lowercase filenames to document IDs.
        """
        if scope == "team":
            field = "team_id"
            index = args.aos_documents_index
        elif scope == "user":
            field = "user_email.keyword"
            index = args.aos_private_documents_index
        else:
            raise ValueError("Invalid scope. Use 'team' or 'user'.")

        query = {
            "query": {"term": {field: value}},
            "_source": ["document_name", "object_store"],
            "size": 1000,
        }

        results = self.client.search(index=index, body=query)

        filename_map = {}

        for hit in results.get("hits", {}).get("hits", []):
            doc_id = hit.get("_id")
            source = hit.get("_source", {})

            doc_name = source.get("document_name")
            if doc_name:
                filename_map[doc_name.lower()] = doc_id
                continue

            obj = source.get("object_store", {})
            for key in ("location", "converted"):
                uri = obj.get(key)
                if isinstance(uri, str):
                    filename_map[PurePosixPath(uri).name.lower()] = doc_id

        return filename_map

    def get_existing_document_uris(self, index: str, s3_paths: list[str]) -> set[str]:
        """
        Check which of the provided S3 paths exist in the given index.

        Checks both 'object_store.converted' and 'object_store.location' fields.
        """
        if not s3_paths:
            return set()

        query = {
            "query": {
                "bool": {
                    "should": [
                        {"terms": {"object_store.converted.keyword": s3_paths}},
                        {"terms": {"object_store.location.keyword": s3_paths}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            "_source": ["object_store"],
            "size": len(s3_paths) * 2,
        }

        try:
            results = self.client.search(index=index, body=query)
        except Exception as e:
            logging.error(f"Failed to query existing document URIs: {e}")
            return set()

        found_uris = set()
        for hit in results.get("hits", {}).get("hits", []):
            obj = hit.get("_source", {}).get("object_store", {})
            converted = obj.get("converted")
            location = obj.get("location")

            if converted and converted in s3_paths:
                found_uris.add(converted)
            if location and location in s3_paths:
                found_uris.add(location)

        logging.debug(f"[get_existing_document_uris] Checked {len(s3_paths)} paths, found {len(found_uris)}.")
        return found_uris
