package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	fastread "github.com/FastR-D/FastRead/backend-go"
	"log"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"
)

func env(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}
func main() {
	if err := run(); err != nil {
		log.Fatal(err)
	}
}
func run() error {
	command := "serve"
	args := os.Args[1:]
	if len(args) > 0 && !strings.HasPrefix(args[0], "-") {
		command = args[0]
		args = args[1:]
	}
	if command == "version" {
		fmt.Println(fastread.Version)
		return nil
	}
	flags := flag.NewFlagSet(command, flag.ContinueOnError)
	root := flags.String("root", env("FASTREAD_WEB_ROOT", "web-data"), "Web data directory")
	listen := flags.String("listen", env("FASTREAD_LISTEN", "127.0.0.1:8483"), "API listen address")
	frontend := flags.String("frontend", env("FASTREAD_FRONTEND_DIST", os.Getenv("FASTREAD_WEB_DIST")), "Optional built frontend directory")
	concurrency := flags.Int("concurrency", 2, "Concurrent worker jobs")
	email := flags.String("email", "", "Account email")
	workspace := flags.String("workspace", "我的资料库", "Workspace name")
	name := flags.String("name", "", "Display name")
	admin := flags.Bool("admin", false, "Create a system administrator")
	if err := flags.Parse(args); err != nil {
		return err
	}
	s, err := fastread.OpenStore(*root)
	if err != nil {
		return err
	}
	defer s.DB.Close()
	switch command {
	case "user-create":
		password := os.Getenv("FASTREAD_INITIAL_PASSWORD")
		if password == "" {
			return errors.New("set FASTREAD_INITIAL_PASSWORD for account creation")
		}
		row, err := s.CreateUser(*email, password, *workspace, *name, *admin)
		if err != nil {
			return err
		}
		return json.NewEncoder(os.Stdout).Encode(row)
	case "invite", "recovery":
		token, err := s.IssueCredential(command, *email)
		if err != nil {
			return err
		}
		return json.NewEncoder(os.Stdout).Encode(fastread.Row{"kind": command, "token": token, "expires_in": 3600})
	case "worker":
		if *concurrency < 1 || *concurrency > 16 {
			return errors.New("concurrency must be between 1 and 16")
		}
		ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
		defer stop()
		return fastread.RunWorker(ctx, s, *concurrency)
	case "serve":
		a := fastread.NewApp(s)
		a.RegisterReading()
		a.RegisterKnowledge()
		a.RegisterIntegrations()
		if err = a.RegisterFastCAS(); err != nil {
			return err
		}
		if err = a.RegisterExchange(); err != nil {
			return err
		}
		if *frontend != "" {
			directory, err := filepath.Abs(*frontend)
			if err != nil {
				return err
			}
			if _, err = os.Stat(filepath.Join(directory, "index.html")); err != nil {
				return fmt.Errorf("frontend index.html: %w", err)
			}
			files := http.FileServer(http.Dir(directory))
			a.Mux.Handle("/", http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if strings.HasPrefix(r.URL.Path, "/api/") {
					http.NotFound(w, r)
					return
				}
				if r.Method != "GET" && r.Method != "HEAD" {
					w.WriteHeader(http.StatusMethodNotAllowed)
					return
				}
				if filepath.Ext(r.URL.Path) == "" {
					http.ServeFile(w, r, filepath.Join(directory, "index.html"))
					return
				}
				files.ServeHTTP(w, r)
			}))
		}
		server := &http.Server{Addr: *listen, Handler: a, ReadHeaderTimeout: 10 * time.Second, ReadTimeout: 120 * time.Second, WriteTimeout: 5 * time.Minute, IdleTimeout: 120 * time.Second}
		ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
		defer stop()
		go func() {
			<-ctx.Done()
			shutdown, cancel := context.WithTimeout(context.Background(), 30*time.Second)
			defer cancel()
			_ = server.Shutdown(shutdown)
		}()
		log.Printf("FastRead %s API listening on %s", fastread.Version, *listen)
		err = server.ListenAndServe()
		if errors.Is(err, http.ErrServerClosed) {
			return nil
		}
		return err
	default:
		return fmt.Errorf("unknown command %q; use serve, worker, user-create, invite, recovery or version", command)
	}
}
