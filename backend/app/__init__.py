from fastapi import FastAPI

def create_app(lifespan) -> FastAPI:
    # Keep package import side-effect free. Routers are runtime composition,
    # not a prerequisite for schema tools or one-shot data migration.
    from .routers import note, provider, model, config, chat, evidence_hub, search_config, interactions

    app = FastAPI(title="FastRead",lifespan=lifespan)
    app.include_router(note.router, prefix="/api")
    app.include_router(provider.router, prefix="/api")
    app.include_router(model.router,prefix="/api")
    app.include_router(config.router,  prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(evidence_hub.router, prefix="/api")
    app.include_router(search_config.router, prefix="/api")
    app.include_router(interactions.router, prefix="/api")

    return app
