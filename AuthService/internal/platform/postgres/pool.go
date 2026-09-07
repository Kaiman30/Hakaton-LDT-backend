package postgres

import (
	"Auth-service/internal/config"
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

// New Создает пул подключения к постгрес
func New(ctx context.Context, cfg config.PostgresConfig) (*pgxpool.Pool, error) {
	dsn := fmt.Sprintf(
		"postgres://%s:%s@%s:%s/%s?sslmode=disable",
		cfg.User, cfg.Password, cfg.Host, cfg.Port, cfg.Database)

	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		return nil, fmt.Errorf("failed to create new pool: %w", err)
	}

	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("failed to ping postgres: %w", err)
	}

	return pool, nil
}
