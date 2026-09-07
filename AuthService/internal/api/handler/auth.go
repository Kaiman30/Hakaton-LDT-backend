package handler

import (
	"Auth-service/internal/auth"
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"net/mail"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
)

type AuthHandler struct {
	repo *auth.Repository
	jwt  *auth.JWTService
}

func NewAuthHandler(repo *auth.Repository, jwt *auth.JWTService) *AuthHandler {
	return &AuthHandler{repo: repo, jwt: jwt}
}

type authResponse struct {
	AccessToken  string    `json:"access_token"`
	RefreshToken string    `json:"refresh_token"`
	TokenType    string    `json:"token_type"`
	User         auth.User `json:"user"`
}

func (h *AuthHandler) Register(w http.ResponseWriter, r *http.Request) {
	var input struct {
		Name     string `json:"name"`
		Email    string `json:"email"`
		Password string `json:"password"`
	}

	if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	if err := validateUserInput(input.Name, input.Email, input.Password); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	passwordHash, err := auth.HashPassword(input.Password)
	if err != nil {
		log.Printf("hash password: %v", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	user := &auth.User{
		Name:         input.Name,
		Email:        input.Email,
		PasswordHash: passwordHash,
		Role:         auth.RoleUser,
	}

	if err := h.repo.CreateUser(r.Context(), user); err != nil {
		if isUniqueViolation(err) {
			writeError(w, http.StatusConflict, "user already exists")
			return
		}
		log.Printf("create user: %v", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	tokens, err := h.jwt.GenerateTokenPair(user.ID, user.Name, user.Role)
	if err != nil {
		log.Printf("generate tokens: %v", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	if err := h.saveRefreshToken(r.Context(), user.ID, tokens.RefreshToken); err != nil {
		log.Printf("save refresh token: %v", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	writeJSON(w, http.StatusCreated, authResponse{
		AccessToken:  tokens.AccessToken,
		RefreshToken: tokens.RefreshToken,
		TokenType:    "Bearer",
		User:         *user,
	})
}

func (h *AuthHandler) CreateUser(w http.ResponseWriter, r *http.Request) {
	var input struct {
		Name     string `json:"name"`
		Email    string `json:"email"`
		Password string `json:"password"`
		Role     string `json:"role"`
	}

	if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	role := strings.ToLower(strings.TrimSpace(input.Role))
	if !isValidRole(role) {
		writeError(w, http.StatusBadRequest, "invalid role")
		return
	}

	if err := validateUserInput(input.Name, input.Email, input.Password); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	passwordHash, err := auth.HashPassword(input.Password)
	if err != nil {
		log.Printf("hash password: %v", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	user := &auth.User{
		Name:         input.Name,
		Email:        input.Email,
		PasswordHash: passwordHash,
		Role:         role,
	}

	if err := h.repo.CreateUser(r.Context(), user); err != nil {
		if isUniqueViolation(err) {
			writeError(w, http.StatusConflict, "user already exists")
			return
		}
		log.Printf("create user: %v", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	writeJSON(w, http.StatusCreated, user)
}

func (h *AuthHandler) Login(w http.ResponseWriter, r *http.Request) {
	var input struct {
		Login    string `json:"login"`
		Password string `json:"password"`
	}

	if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	if strings.TrimSpace(input.Login) == "" || strings.TrimSpace(input.Password) == "" {
		writeError(w, http.StatusUnauthorized, "invalid credentials")
		return
	}

	user, err := h.repo.GetUserByNameOrEmail(r.Context(), input.Login)
	if err != nil {
		if errors.Is(err, auth.ErrNotFound) {
			writeError(w, http.StatusUnauthorized, "invalid credentials")
			return
		}
		log.Printf("get user: %v", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	if !auth.VerifyPassword(user.PasswordHash, input.Password) {
		writeError(w, http.StatusUnauthorized, "invalid credentials")
		return
	}

	tokens, err := h.jwt.GenerateTokenPair(user.ID, user.Name, user.Role)
	if err != nil {
		log.Printf("generate tokens: %v", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	if err := h.saveRefreshToken(r.Context(), user.ID, tokens.RefreshToken); err != nil {
		log.Printf("save refresh token: %v", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	writeJSON(w, http.StatusOK, authResponse{
		AccessToken:  tokens.AccessToken,
		RefreshToken: tokens.RefreshToken,
		TokenType:    "Bearer",
		User:         *user,
	})
}

func (h *AuthHandler) Refresh(w http.ResponseWriter, r *http.Request) {
	var input struct {
		RefreshToken string `json:"refresh_token"`
	}

	if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	claims, err := h.jwt.ParseToken(input.RefreshToken)
	if err != nil || claims.TokenType != "refresh" {
		writeError(w, http.StatusUnauthorized, "invalid refresh token")
		return
	}

	tokenHash := auth.HashRefreshToken(input.RefreshToken)
	stored, err := h.repo.GetRefreshTokenByHash(r.Context(), tokenHash)
	if err != nil {
		if errors.Is(err, auth.ErrNotFound) {
			writeError(w, http.StatusUnauthorized, "invalid refresh token")
			return
		}
		log.Printf("get refresh token: %v", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	if stored.Revoked || stored.ExpiresAt.Before(time.Now()) || stored.UserID != claims.UserID {
		writeError(w, http.StatusUnauthorized, "invalid refresh token")
		return
	}

	if err := h.repo.RevokeRefreshToken(r.Context(), stored.ID); err != nil {
		log.Printf("revoke refresh token: %v", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	user, err := h.repo.GetUserByID(r.Context(), claims.UserID)
	if err != nil {
		log.Printf("get user: %v", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	tokens, err := h.jwt.GenerateTokenPair(user.ID, user.Name, user.Role)
	if err != nil {
		log.Printf("generate tokens: %v", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	if err := h.saveRefreshToken(r.Context(), user.ID, tokens.RefreshToken); err != nil {
		log.Printf("save refresh token: %v", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	writeJSON(w, http.StatusOK, authResponse{
		AccessToken:  tokens.AccessToken,
		RefreshToken: tokens.RefreshToken,
		TokenType:    "Bearer",
		User:         *user,
	})
}

func (h *AuthHandler) Logout(w http.ResponseWriter, r *http.Request) {
	var input struct {
		RefreshToken string `json:"refresh_token"`
	}

	if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	tokenHash := auth.HashRefreshToken(input.RefreshToken)
	stored, err := h.repo.GetRefreshTokenByHash(r.Context(), tokenHash)
	if err != nil {
		if errors.Is(err, auth.ErrNotFound) {
			writeError(w, http.StatusUnauthorized, "invalid refresh token")
			return
		}
		log.Printf("get refresh token: %v", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	if err := h.repo.RevokeRefreshToken(r.Context(), stored.ID); err != nil {
		log.Printf("revoke refresh token: %v", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{"status": "logged_out"})
}

func (h *AuthHandler) Me(w http.ResponseWriter, r *http.Request) {
	user, ok := r.Context().Value(UserContextKey).(*auth.User)
	if !ok {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return
	}

	writeJSON(w, http.StatusOK, user)
}

func (h *AuthHandler) UpdateRole(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	if id == "" {
		writeError(w, http.StatusBadRequest, "invalid user id")
		return
	}

	var input struct {
		Role string `json:"role"`
	}

	if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	role := strings.ToLower(strings.TrimSpace(input.Role))
	if !isValidRole(role) {
		writeError(w, http.StatusBadRequest, "invalid role")
		return
	}

	if err := h.repo.UpdateUserRole(r.Context(), id, role); err != nil {
		if errors.Is(err, auth.ErrNotFound) {
			writeError(w, http.StatusNotFound, "user not found")
			return
		}
		log.Printf("update user role: %v", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{"status": "updated"})
}

func (h *AuthHandler) ListUsers(w http.ResponseWriter, r *http.Request) {
	users, err := h.repo.ListUsers(r.Context())
	if err != nil {
		log.Printf("list users: %v", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	writeJSON(w, http.StatusOK, users)
}

func (h *AuthHandler) GetUser(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	if id == "" {
		writeError(w, http.StatusBadRequest, "invalid user id")
		return
	}

	user, err := h.repo.GetUserByID(r.Context(), id)
	if err != nil {
		if errors.Is(err, auth.ErrNotFound) {
			writeError(w, http.StatusNotFound, "user not found")
			return
		}
		log.Printf("get user: %v", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	writeJSON(w, http.StatusOK, user)
}

func (h *AuthHandler) UpdateUser(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	if id == "" {
		writeError(w, http.StatusBadRequest, "invalid user id")
		return
	}

	var input struct {
		Name     string `json:"name"`
		Email    string `json:"email"`
		Password string `json:"password"`
		Role     string `json:"role"`
	}

	if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	updates := &auth.User{}
	if input.Name != "" {
		if len(input.Name) < 3 || len(input.Name) > 64 {
			writeError(w, http.StatusBadRequest, "name must be between 3 and 64 characters")
			return
		}
		updates.Name = input.Name
	}
	if input.Email != "" {
		if _, err := mail.ParseAddress(input.Email); err != nil {
			writeError(w, http.StatusBadRequest, "invalid email")
			return
		}
		updates.Email = input.Email
	}
	if input.Password != "" {
		if len(input.Password) < 8 {
			writeError(w, http.StatusBadRequest, "password must be at least 8 characters")
			return
		}
		passwordHash, err := auth.HashPassword(input.Password)
		if err != nil {
			log.Printf("hash password: %v", err)
			writeError(w, http.StatusInternalServerError, "internal error")
			return
		}
		updates.PasswordHash = passwordHash
	}
	if input.Role != "" {
		role := strings.ToLower(strings.TrimSpace(input.Role))
		if !isValidRole(role) {
			writeError(w, http.StatusBadRequest, "invalid role")
			return
		}
		updates.Role = role
	}

	if err := h.repo.UpdateUser(r.Context(), id, updates); err != nil {
		if errors.Is(err, auth.ErrNotFound) {
			writeError(w, http.StatusNotFound, "user not found")
			return
		}
		if errors.Is(err, auth.ErrAlreadyExists) {
			writeError(w, http.StatusConflict, "user already exists")
			return
		}
		log.Printf("update user: %v", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{"status": "updated"})
}

func (h *AuthHandler) DeleteUser(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	if id == "" {
		writeError(w, http.StatusBadRequest, "invalid user id")
		return
	}

	if err := h.repo.DeleteUser(r.Context(), id); err != nil {
		if errors.Is(err, auth.ErrNotFound) {
			writeError(w, http.StatusNotFound, "user not found")
			return
		}
		log.Printf("delete user: %v", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{"status": "deleted"})
}

func (h *AuthHandler) saveRefreshToken(ctx context.Context, userID, token string) error {
	tokenHash := auth.HashRefreshToken(token)
	expiresAt := time.Now().Add(auth.RefreshTokenTTL)
	return h.repo.CreateRefreshToken(ctx, &auth.RefreshToken{
		UserID:    userID,
		TokenHash: tokenHash,
		ExpiresAt: expiresAt,
	})
}

func validateUserInput(name, email, password string) error {
	if len(name) < 3 || len(name) > 64 {
		return errors.New("name must be between 3 and 64 characters")
	}

	if _, err := mail.ParseAddress(email); err != nil {
		return errors.New("invalid email")
	}

	if len(password) < 8 {
		return errors.New("password must be at least 8 characters")
	}

	return nil
}

func isValidRole(role string) bool {
	return role == auth.RoleUser || role == auth.RoleAdmin || role == auth.RoleMedia
}

func isUniqueViolation(err error) bool {
	return strings.Contains(err.Error(), "duplicate") || strings.Contains(err.Error(), "unique")
}
