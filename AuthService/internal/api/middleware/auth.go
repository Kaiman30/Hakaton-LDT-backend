package middleware

import (
	"Auth-service/internal/api/handler"
	"Auth-service/internal/auth"
	"context"
	"net/http"
	"strings"
)

type contextKey string

const UserContextKey contextKey = "user"

func AuthRequired(jwtService *auth.JWTService, repo *auth.Repository, allowedRoles ...string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			authorization := r.Header.Get("Authorization")
			parts := strings.SplitN(authorization, " ", 2)
			if len(parts) != 2 || !strings.EqualFold(parts[0], "Bearer") {
				handler.WriteError(w, http.StatusUnauthorized, "missing bearer token")
				return
			}

			claims, err := jwtService.ParseToken(strings.TrimSpace(parts[1]))
			if err != nil || claims.TokenType != "access" {
				handler.WriteError(w, http.StatusUnauthorized, "invalid access token")
				return
			}

			user, err := repo.GetUserByID(r.Context(), claims.UserID)
			if err != nil {
				handler.WriteError(w, http.StatusUnauthorized, "invalid access token")
				return
			}

			if len(allowedRoles) > 0 && !containsRole(allowedRoles, user.Role) {
				handler.WriteError(w, http.StatusForbidden, "forbidden")
				return
			}

			ctx := context.WithValue(r.Context(), handler.UserContextKey, user)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func containsRole(roles []string, target string) bool {
	for _, role := range roles {
		if role == target {
			return true
		}
	}
	return false
}
