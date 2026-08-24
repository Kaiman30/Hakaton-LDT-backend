package config

import "github.com/kelseyhightower/envconfig"

type Config struct {
	HTTP HTTPConfig
}

type HTTPConfig struct {
	Port string `envconfig:"HTTP_PORT" default:"8000"`
}

func Load() (*Config, error) {
	var cfg Config
	if err := envconfig.Process("", &cfg); err != nil {
		return nil, err
	}

	return &cfg, nil
}
