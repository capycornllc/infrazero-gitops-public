# Аудит infrazero-gitops-public

## КРИТИЧЕСКИЕ

### 1. Placeholder значения не заменяются автоматически
- `platform/infisical/secretproviderclass.yaml`: `identityId: "REPLACE_ME"`, `projectId: "REPLACE_ME"`, `infisicalUrl: "https://infisical.example.com"`
- `platform/cert-manager/cluster-issuers.yaml`: `email: admin@example.com` (staging и prod)
- `clusters/*/project.yaml`: `sourceRepos: https://github.com/your-org/your-repo` (3 файла)
- `clusters/*/applications/platform/*.yaml`: `repoURL: https://github.com/your-org/your-repo` (12+ файлов)
- `config/apps/example.yaml`: `repoURL`, `baseDomain`, `repository` — всё placeholder'ы
- `platform/pgbouncer/pgbouncer-services.yaml`: `ip: "PGBOUNCER_IP_PLACEHOLDER"` (write и read endpoints)
**Действие:** Добавить CI check что ни один placeholder не попал в main. Или автоматизировать замену при деплое.

### 2. Bootstrap Job — неполная обработка ошибок
- `clusters/dev/bootstrap/infisical-k8s-auth/configmap.yaml` (entrypoint.sh):
  - Token reviewer secret loop (30 итераций × 2s) — нет сообщения о таймауте если токен не появился
  - `API_STATUS` / `API_BODY` используются в `require_success()` но могут быть не установлены если `api_call()` не вызывался
  - Нет exponential backoff в retry логике

### 3. Broken cross-references
- `apps/root/application.yaml` хардкодит `clusters/dev` — не работает для test/prod
- `pgbouncer.yaml` ссылается на `platform/pgbouncer` с `PGBOUNCER_IP_PLACEHOLDER` — нет механизма замены
- `infisical-secretproviderclass.yaml` ссылается на template с `REPLACE_ME`

## ВЫСОКИЙ ПРИОРИТЕТ

### 4. Overly permissive RBAC
- `clusters/*/project.yaml`: `clusterResourceWhitelist: group: "*", kind: "*"` — разрешает всё
**Действие:** Ограничить до конкретных API groups для production.

### 5. Нет network policies
- Все workloads могут общаться друг с другом без ограничений
**Действие:** Добавить NetworkPolicy для каждого namespace.

### 6. Schema validation gaps
- `schemas/app-config.schema.json`:
  - `bootstrap.env` принимает любую строку (нет enum `["dev", "test", "prod"]`)
  - `global.baseDomain` нет format validation
  - `workload.type: "Job"` не требует `schedule` (только CronJob)
  - `workload.command` принимает массив но не валидирует что элементы непустые
  - Нет валидации портов (1-65535)

### 7. GitHub Actions workflow
- `python -m unittest discover -s tests` упадёт если директория tests не существует
- Нет проверки что `schemas/app-config.schema.json` существует перед использованием
- Workflow dispatch payload не валидируется как JSON перед передачей в скрипт

## СРЕДНИЙ ПРИОРИТЕТ

### 8. Python скрипты
- `generate_app_config.py`:
  - `load_payload()` не валидирует JSON формат env variable перед парсингом
  - `split_image()` не обрабатывает None/empty gracefully
  - `normalize_working_directory()` молча fallback'ит на `/app` без логирования
  - `normalize_ports()` не валидирует диапазон портов (1-65535)
- `validate_app_config.py`:
  - Нет проверки существования файлов перед чтением
  - Generic exception handling не различает file not found, invalid YAML, schema error

### 9. Kubernetes manifests
- `job.yaml`: `image: alpine:3.19` с `IfNotPresent` — нет digest для reproducibility
- `secrets-store-csi.yaml`: `tokenRequests[0].audience: infisical` хардкодит — должно быть per-environment
- Нет resource limits/quotas ни в одном namespace

### 10. Нет различий между environments
- dev/test/prod используют одинаковые настройки cert-manager, Infisical, resource limits
- В production нужны stricter RBAC, resource limits, network policies

## НИЗКИЙ ПРИОРИТЕТ

### 11. Нет .gitignore для generated files
- `.tmp/` директория должна быть в .gitignore

### 12. Нет pre-commit hooks
- Валидация YAML синтаксиса и schema compliance

### 13. Документация
- Нет troubleshooting guide для bootstrap failures
- Нет примеров кастомизации SecretProviderClass
- Нет migration guide old → new payload shape

## БЕЗОПАСНОСТЬ

1. ArgoCD Projects разрешают `group: "*", kind: "*"` — ограничить для prod
2. Нет network policies — все pods могут общаться
3. Bootstrap job ожидает секреты в `kube-system` — нет валидации существования
4. Token reviewer JWT long-lived без ротации
5. Placeholder'ы в production приведут к silent failure
