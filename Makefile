.PHONY: help dev down migrate logs \
        bootstrap-apply \
        infra-init infra-plan infra-apply infra-destroy \
        ansible-check ansible-deploy ansible-deploy-tag

# Default target — print help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' | sort

# ── Local development (Docker Compose) ───────────────────────────────────────

dev: ## Build and start all services locally
	docker compose up --build

down: ## Stop and remove all local containers
	docker compose down

migrate: ## Run Alembic migrations inside the running backend container
	docker compose exec backend alembic upgrade head

logs: ## Tail logs from all containers (Ctrl-C to stop)
	docker compose logs -f

# ── Terraform (AWS infrastructure) ───────────────────────────────────────────

bootstrap-apply: ## (One-time) Create S3 state bucket and DynamoDB lock table
	cd infra/bootstrap && terraform init && terraform apply

infra-init: ## Init Terraform — migrates state into S3 after bootstrap
	cd infra && terraform init

infra-plan: ## Preview infrastructure changes (dry run)
	cd infra && terraform plan

infra-apply: ## Apply infrastructure changes to AWS
	cd infra && terraform apply

infra-destroy: ## Destroy all AWS infrastructure (destructive!)
	cd infra && terraform destroy

# ── Ansible (VM / bare-metal provisioning) ───────────────────────────────────

INVENTORY ?= infra/ansible/inventory/hosts.ini

ansible-check: ## Dry-run the full playbook (no changes made)
	ansible-playbook infra/ansible/site.yml -i $(INVENTORY) --check --diff

ansible-deploy: ## Provision and deploy to all servers in inventory
	ansible-playbook infra/ansible/site.yml -i $(INVENTORY)

ansible-deploy-tag: ## Run a single role (usage: make ansible-deploy-tag TAG=docker)
	ansible-playbook infra/ansible/site.yml -i $(INVENTORY) --tags $(TAG)
