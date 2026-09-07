package middleware

import (
	"encoding/json"
	"net/http"
	"strings"

	"github.com/golang-jwt/jwt/v5"
)

// roleAny is a sentinel that means "any authenticated user", regardless of role
const roleAny = "any"

type rule struct {
	prefix  string
	methods map[string]struct{}
	roles   []string // empty = public; roleAny = require valid token; "admin" = require admin role
}

// JWT returns a middleware that enforces the gateway's authorization rules.
// It validates Bearer tokens locally using shared HS256 secret
func JWT(secret string) func(http.Handler) http.Handler {
	post := methodSet(http.MethodPost)
	get := methodSet(http.MethodGet)
	mutating := methodSet(http.MethodPost, http.MethodPut, http.MethodPatch, http.MethodDelete)

	rules := []rule{
		// public exceptions
		{prefix: "/api/v1/auth/login", methods: post},
		{prefix: "/api/v1/auth/refresh", methods: post},

		// Authenticated, no specific role
		{prefix: "/api/v1/auth/me", methods: get, roles: []string{roleAny}},

		// Admin-only user management
		{prefix: "/api/v1/auth/users", methods: get, roles: []string{"admin"}},
		{prefix: "/api/v1/auth/users", methods: mutating, roles: []string{"admin"}},
		{prefix: "/api/v1/auth/register", methods: post, roles: []string{"admin"}},

		// Any remaining mutating request under /api/v1 requires a valid token
		{prefix: "/api/v1/", methods: mutating, roles: []string{roleAny}},
	}

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			required := requiredRoles(r, rules)
			if required == nil {
				next.ServeHTTP(w, r)
				return
			}

			token, err := extractBearer(r)
			if err != nil {
				writeError(w, http.StatusUnauthorized, "missing or invalid authorization header")
				return
			}

			claims, err := parseToken(token, secret)
			if err != nil {
				writeError(w, http.StatusUnauthorized, "invalid token")
				return
			}

			if !hasRole(required, claims.Role) {
				writeError(w, http.StatusForbidden, "forbidden")
				return
			}

			r.Header.Set("X-User-ID", claims.UserID)
			r.Header.Set("X-User-Name", claims.Name)
			r.Header.Set("X-Role", claims.Role)

			next.ServeHTTP(w, r)
		})
	}
}

type Claims struct {
	UserID string `json:"user_id"`
	Name   string `json:"name"`
	Role   string `json:"role"`
	jwt.RegisteredClaims
}

func parseToken(tokenString, secret string) (*Claims, error) {
	token, err := jwt.ParseWithClaims(tokenString, &Claims{}, func(token *jwt.Token) (interface{}, error) {
		return []byte(secret), nil
	})
	if err != nil {
		return nil, err
	}
	if claims, ok := token.Claims.(*Claims); ok && token.Valid {
		return claims, nil
	}
	return nil, jwt.ErrSignatureInvalid
}

func requiredRoles(r *http.Request, rules []rule) []string {
	path := r.URL.Path
	method := r.Method

	for _, rule := range rules {
		if !strings.HasPrefix(path, rule.prefix) {
			continue
		}
		if len(rule.methods) > 0 {
			if _, ok := rule.methods[method]; !ok {
				continue
			}
		}
		return rule.roles
	}
	return nil
}

func extractBearer(r *http.Request) (string, error) {
	h := r.Header.Get("Authorization")
	if h == "" {
		return "", jwt.ErrTokenMalformed
	}
	const prefix = "Bearer "
	if !strings.HasPrefix(h, prefix) {
		return "", jwt.ErrTokenMalformed
	}
	return strings.TrimPrefix(h, prefix), nil
}

func methodSet(methods ...string) map[string]struct{} {
	set := make(map[string]struct{}, len(methods))
	for _, m := range methods {
		set[m] = struct{}{}
	}
	return set
}

func hasRole(required []string, actual string) bool {
	for _, role := range required {
		if role == roleAny {
			return true
		}
		if role == actual {
			return true
		}
	}
	return false
}

func writeError(w http.ResponseWriter, status int, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]string{"error": message})
}
