package api

import (
	"Hakaton-LDT.API-Gateway/internal/api/handler"
	"Hakaton-LDT.API-Gateway/internal/config"
	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
)

func NewRouter(cfg *config.Config) (*chi.Mux, error) {
	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)

	r.Get("/health", handler.Health(cfg))

	return r, nil
}
