package handler

import (
	"encoding/json"
	"net/http"

	"Hakaton-LDT.API-Gateway/internal/config"
)

func Health(cfg *config.Config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"Gateway status": "running",
		})
	}
}
