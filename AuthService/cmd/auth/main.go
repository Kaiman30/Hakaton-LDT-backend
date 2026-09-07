package main

import (
	"Auth-service/internal/api"
	"Auth-service/internal/config"
	"Auth-service/internal/platform/postgres"
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	// Инициализация конфига
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("load config: %v", err)
	}

	// Graceful shutdown
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	// Пул подключений
	pool, err := postgres.New(ctx, cfg.Postgres)
	if err != nil {
		log.Fatalf("init pool: %v", err)
	}
	defer pool.Close()

	log.Println("connected to postgres")

	// Запуск сервера
	srv := &http.Server{
		Addr:    fmt.Sprintf(":%s", cfg.HTTP.Port),
		Handler: api.NewRouter(pool, cfg.JWT.Secret),
	}

	go func() {
		log.Printf("server listening on port %s", cfg.HTTP.Port)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("server error: %v", err)
		}
	}()
	<-ctx.Done()

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	if err := srv.Shutdown(shutdownCtx); err != nil {
		log.Fatalf("server shutdown: %v", err)
	}

	log.Println("server shutdown complete")
}
