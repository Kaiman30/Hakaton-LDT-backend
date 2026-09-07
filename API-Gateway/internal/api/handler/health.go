package handler

import (
	"encoding/json"
	"fmt"
	"net/http"

	"Hakaton-LDT.API-Gateway/internal/config"
)

func Health(cfg *config.Config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		authStatus := checkService(cfg.Auth.Host, cfg.Auth.Port)
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{

			"API-Gateway": "running",
			"AuthService": authStatus,
		})
	}
}

func checkService(host, port string) string {
	resp, err := http.Get(fmt.Sprintf("http://%s:%s/health", host, port))
	if err != nil {
		return "unreachable: " + err.Error()
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Sprintf("unhealthy: status %d", resp.StatusCode)
	}
	return "running"
}
