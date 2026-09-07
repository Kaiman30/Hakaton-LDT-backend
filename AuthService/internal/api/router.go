package api

import (
	"Auth-service/internal/api/handler"
	"Auth-service/internal/api/middleware"
	"Auth-service/internal/auth"

	"github.com/go-chi/chi/v5"
	chimiddleware "github.com/go-chi/chi/v5/middleware"
	"github.com/jackc/pgx/v5/pgxpool"
)

func NewRouter(pool *pgxpool.Pool, jwtSecret string) *chi.Mux {
	r := chi.NewRouter()
	r.Use(chimiddleware.Logger)
	r.Use(chimiddleware.Recoverer)

	repo := auth.NewRepository(pool)
	jwtService := auth.NewJWTService(jwtSecret)
	authHandler := handler.NewAuthHandler(repo, jwtService)
	authRequired := middleware.AuthRequired(jwtService, repo)
	adminRequired := middleware.AuthRequired(jwtService, repo, auth.RoleAdmin)

	r.Get("/health", handler.Health)

	r.Post("/register", authHandler.Register)
	r.Post("/login", authHandler.Login)
	r.Post("/refresh", authHandler.Refresh)
	r.Post("/logout", authHandler.Logout)
	r.With(authRequired).Get("/me", authHandler.Me)
	r.With(adminRequired).Get("/users", authHandler.ListUsers)
	r.With(adminRequired).Post("/users", authHandler.CreateUser)
	r.With(adminRequired).Get("/users/{id}", authHandler.GetUser)
	r.With(adminRequired).Patch("/users/{id}", authHandler.UpdateUser)
	r.With(adminRequired).Delete("/users/{id}", authHandler.DeleteUser)
	r.With(adminRequired).Patch("/users/{id}/role", authHandler.UpdateRole)

	return r
}
