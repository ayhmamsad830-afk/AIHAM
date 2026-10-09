import uvicorn
from app.main import create_app
from app.config import config

if __name__ == "__main__":
    app = create_app()

    uvicorn_config = uvicorn.Config(
        app=app,
        host=config.HOST,
        port=config.PORT,
        workers=1,
        ws_max_size=16777216,
        ws_ping_interval=60,
        ws_ping_timeout=120,
        loop="auto",
        ws="websockets",
        log_level="info",
        timeout_keep_alive=600
    )

    server = uvicorn.Server(uvicorn_config)
    server.run()
