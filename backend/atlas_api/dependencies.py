"""Acceso al estado residente de la aplicación."""

from fastapi import Request

from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever


def get_retriever(request: Request) -> CrossText2LocRetriever:
    retriever = getattr(request.app.state, "retriever", None)
    if retriever is None:
        from .errors import ApiServiceUnavailable
        raise ApiServiceUnavailable("RUNTIME_NOT_READY", "El recuperador todavía no está disponible.")
    return retriever
