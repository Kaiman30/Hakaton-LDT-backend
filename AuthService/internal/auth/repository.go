package auth

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

const pgUniqueViolation = "23505"

var (
	ErrNotFound      = errors.New("not found")
	ErrAlreadyExists = errors.New("already exists")
)

type Repository struct {
	pool *pgxpool.Pool
}

func NewRepository(pool *pgxpool.Pool) *Repository {
	return &Repository{pool: pool}
}

func isUniqueViolation(err error) bool {
	var pgErr *pgconn.PgError
	return errors.As(err, &pgErr) && pgErr.Code == pgUniqueViolation
}

func (r *Repository) CreateUser(ctx context.Context, user *User) error {
	return r.pool.QueryRow(ctx, `
		INSERT INTO users (name, email, password_hash, role)
		VALUES ($1, $2, $3, $4)
		RETURNING id::text, created_at, updated_at`,
		user.Name, user.Email, user.PasswordHash, user.Role,
	).Scan(&user.ID, &user.CreatedAt, &user.UpdatedAt)
}

func (r *Repository) GetUserByID(ctx context.Context, id string) (*User, error) {
	row, err := r.pool.Query(ctx, `
		SELECT id::text, name, email, password_hash, role, created_at, updated_at
		FROM users
		WHERE id = $1`, id)
	if err != nil {
		return nil, fmt.Errorf("query user: %w", err)
	}

	user, err := pgx.CollectOneRow(row, pgx.RowToStructByName[User])
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("collect user: %w", err)
	}
	return &user, nil
}

func (r *Repository) GetUserByNameOrEmail(ctx context.Context, login string) (*User, error) {
	row, err := r.pool.Query(ctx, `
		SELECT id::text, name, email, password_hash, role, created_at, updated_at
		FROM users
		WHERE name = $1 OR email = $1`, login)
	if err != nil {
		return nil, fmt.Errorf("query user: %w", err)
	}

	user, err := pgx.CollectOneRow(row, pgx.RowToStructByName[User])
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("collect user: %w", err)
	}
	return &user, nil
}

func (r *Repository) UpdateUserRole(ctx context.Context, id, role string) error {
	cmd, err := r.pool.Exec(ctx, `
		UPDATE users
		SET role = $2, updated_at = now()
		WHERE id = $1`, id, role)
	if err != nil {
		return fmt.Errorf("update user role: %w", err)
	}
	if cmd.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (r *Repository) ListUsers(ctx context.Context) ([]User, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT id::text, name, email, password_hash, role, created_at, updated_at
		FROM users
		ORDER BY created_at DESC`)
	if err != nil {
		return nil, fmt.Errorf("query users: %w", err)
	}
	defer rows.Close()

	users, err := pgx.CollectRows(rows, pgx.RowToStructByName[User])
	if err != nil {
		return nil, fmt.Errorf("collect users: %w", err)
	}
	return users, nil
}

func (r *Repository) UpdateUser(ctx context.Context, id string, updates *User) error {
	fields := []string{}
	args := []any{}
	argNum := 1

	if updates.Name != "" {
		fields = append(fields, fmt.Sprintf("name = $%d", argNum))
		args = append(args, updates.Name)
		argNum++
	}
	if updates.Email != "" {
		fields = append(fields, fmt.Sprintf("email = $%d", argNum))
		args = append(args, updates.Email)
		argNum++
	}
	if updates.Role != "" {
		fields = append(fields, fmt.Sprintf("role = $%d", argNum))
		args = append(args, updates.Role)
		argNum++
	}
	if updates.PasswordHash != "" {
		fields = append(fields, fmt.Sprintf("password_hash = $%d", argNum))
		args = append(args, updates.PasswordHash)
		argNum++
	}

	if len(fields) == 0 {
		return ErrNotFound
	}

	args = append(args, id)
	query := fmt.Sprintf("UPDATE users SET %s, updated_at = now() WHERE id = $%d", strings.Join(fields, ", "), argNum)

	cmd, err := r.pool.Exec(ctx, query, args...)
	if err != nil {
		if isUniqueViolation(err) {
			return ErrAlreadyExists
		}
		return fmt.Errorf("update user: %w", err)
	}
	if cmd.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (r *Repository) DeleteUser(ctx context.Context, id string) error {
	cmd, err := r.pool.Exec(ctx, `DELETE FROM users WHERE id = $1`, id)
	if err != nil {
		return fmt.Errorf("delete user: %w", err)
	}
	if cmd.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (r *Repository) CreateRefreshToken(ctx context.Context, token *RefreshToken) error {
	return r.pool.QueryRow(ctx, `
		INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
		VALUES ($1, $2, $3)
		RETURNING id::text, created_at`,
		token.UserID, token.TokenHash, token.ExpiresAt,
	).Scan(&token.ID, &token.CreatedAt)
}

func (r *Repository) GetRefreshTokenByHash(ctx context.Context, hash string) (*RefreshToken, error) {
	row, err := r.pool.Query(ctx, `
		SELECT id::text, user_id::text, token_hash, expires_at, revoked, created_at
		FROM refresh_tokens
		WHERE token_hash = $1`, hash)
	if err != nil {
		return nil, fmt.Errorf("query refresh token: %w", err)
	}

	token, err := pgx.CollectOneRow(row, pgx.RowToStructByName[RefreshToken])
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("collect refresh token: %w", err)
	}
	return &token, nil
}

func (r *Repository) RevokeRefreshToken(ctx context.Context, id string) error {
	_, err := r.pool.Exec(ctx, `
		UPDATE refresh_tokens
		SET revoked = true
		WHERE id = $1`, id)
	if err != nil {
		return fmt.Errorf("revoke refresh token: %w", err)
	}
	return nil
}
