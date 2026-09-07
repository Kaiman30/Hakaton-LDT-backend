package auth

import "time"

const (
	RoleUser  = "user"
	RoleAdmin = "admin"
	RoleMedia = "media"
)

type User struct {
	ID           string    `db:"id" json:"id"`
	Name         string    `db:"name" json:"name"`
	Email        string    `db:"email" json:"email"`
	PasswordHash string    `db:"password_hash" json:"-"`
	Role         string    `db:"role" json:"role"`
	CreatedAt    time.Time `db:"created_at" json:"created_at"`
	UpdatedAt    time.Time `db:"updated_at" json:"updated_at"`
}

type RefreshToken struct {
	ID        string    `db:"id" json:"id"`
	UserID    string    `db:"user_id" json:"user_id"`
	TokenHash string    `db:"token_hash" json:"-"`
	ExpiresAt time.Time `db:"expires_at" json:"expires_at"`
	Revoked   bool      `db:"revoked" json:"revoked"`
	CreatedAt time.Time `db:"created_at" json:"created_at"`
}
