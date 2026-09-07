package api

import (
	"net/http"
	"net/http/httputil"
	"net/url"

	"Hakaton-LDT.API-Gateway/internal/api/handler"
	gwMiddleware "Hakaton-LDT.API-Gateway/internal/api/middleware"
	"Hakaton-LDT.API-Gateway/internal/config"
	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/go-chi/cors"
)

func NewRouter(cfg *config.Config) (*chi.Mux, error) {
	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(cors.Handler(cors.Options{
		AllowedOrigins:   []string{"http://localhost:5173", "http://127.0.0.1:5173"},
		AllowedMethods:   []string{"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"},
		AllowedHeaders:   []string{"Accept", "Authorization", "Content-Type", "X-Requested-With"},
		ExposedHeaders:   []string{"Link"},
		AllowCredentials: true,
		MaxAge:           300,
	}))
	r.Use(gwMiddleware.JWT(cfg.JWTSecret))

	authProxy, err := newReverseProxy(cfg.Auth.Host, cfg.Auth.Port)
	if err != nil {
		return nil, err
	}

	r.Get("/health", handler.Health(cfg))

	r.Mount("/api/v1/auth", http.StripPrefix("/api/v1/auth", authProxy))

	return r, nil
}

// proxyWithPath proxies the request to the given upstream path,
// regardless of the original request path
func proxyWithPath(proxy *httputil.ReverseProxy, path string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		r.URL.Path = path
		proxy.ServeHTTP(w, r)
	}
}

func newReverseProxy(host, port string) (*httputil.ReverseProxy, error) {
	target, err := url.Parse("http://" + host + ":" + port)
	if err != nil {
		return nil, err
	}

	return httputil.NewSingleHostReverseProxy(target), nil
}
