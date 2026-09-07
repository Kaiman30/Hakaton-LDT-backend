package config

import "github.com/kelseyhightower/envconfig"

type Config struct {
	HTTP      HTTPConfig
	JWTSecret string `envconfig:"JWT_SECRET" default:"dev-secret"`
	Auth      AuthConfig
}

type HTTPConfig struct {
	Port string `envconfig:"HTTP_PORT" default:"8000"`
}

type AuthConfig struct {
	Host string `envconfig:"HOST" default:"localhost"`
	Port string `envconfig:"PORT" default:"8001"`
}

func Load() (*Config, error) {
	var cfg Config
	if err := envconfig.Process("", &cfg); err != nil {
		return nil, err
	}

	return &cfg, nil
}
