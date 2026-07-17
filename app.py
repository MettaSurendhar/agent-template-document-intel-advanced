from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import args
from api.exceptions.custom_exceptions import APIException, api_exception_handler
from api.middleware.auth_middleware import auth_middleware
from api.routers import agents, audit, auth, documents, emails, private_search, teams, users
from api.utils.logging_utils import setup_logging

load_dotenv()
setup_logging()
app = FastAPI()

app.middleware("http")(auth_middleware)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.add_exception_handler(APIException, api_exception_handler)

app.include_router(auth.router, prefix=args.subpath)
app.include_router(teams.router, prefix=args.subpath)
app.include_router(documents.router, prefix=args.subpath)
app.include_router(agents.router, prefix=args.subpath)
app.include_router(emails.router, prefix=args.subpath)
app.include_router(audit.router, prefix=args.subpath)
app.include_router(private_search.router, prefix=args.subpath)
app.include_router(users.router, prefix=args.subpath)


@app.get(f"{args.subpath}/ping")
async def ping():
    """Return a status-OK if the endpoint is reachable."""
    return {"status": "OK"}


if __name__ == "__main__":
    import uvicorn

    uvicorn_kwargs = {
        "app": "app:app",
        "host": args.host,
        "port": int(args.port),
        "workers": 1,
    }

    # Enable HTTPS only if cert & key are provided
    if args.ssl_keyfile and args.ssl_certfile:
        uvicorn_kwargs["ssl_keyfile"] = args.ssl_keyfile
        uvicorn_kwargs["ssl_certfile"] = args.ssl_certfile

        print("Starting server with HTTPS")
    else:
        print("Starting server with HTTP")

    uvicorn.run(**uvicorn_kwargs)
