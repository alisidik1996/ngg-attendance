from core.app import create_app

app = create_app(serve_static=True, docs_enabled=True)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=2424, reload=True)
