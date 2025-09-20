# 📦 infra-boomer  
_A Terraform PR action with lint, plan, cost, and merge muscles._  

[![License](https://img.shields.io/badge/license-Apache--2.0-green)](./LICENSE)  
[![GitHub Actions](https://img.shields.io/badge/GitHub-Actions-blue)](#)  

**infra-boomer** helps teams keep Terraform clean and predictable:  
- 🧹 **TFLint** to catch style & security issues.  
- 🚀 **Terraform plan/apply** in PRs and merges.  
- 💸 **Infracost** for cost visibility (optional).  
- 📣 **Slack notifications** for merge failures or cost roll-ups.  

---

## 🔧 Features  

- **PR mode**:  
  - Runs `terraform fmt`, `validate`, `plan`.  
  - TFLint with repo or default baseline config.  
  - Optional Infracost comment (cost diff vs base).  
  - PR comments are automatically updated (no duplicates).  

- **Merge mode**:  
  - Re-runs Terraform plan.  
  - Optionally runs `terraform apply` (`terraform_apply: true`).  
  - If Infracost is enabled, generates per-folder cost diff JSON and posts Slack alerts on failure.  

- **Rollup mode**:  
  - Aggregates per-folder cost JSON from merge jobs.  
  - Optionally posts one Slack message with total cost changes.  

---

## 📂 Modes Explained  

| Mode    | Purpose | Key Outputs | Typical Use |
|---------|---------|-------------|-------------|
| `pr`    | Validate incoming changes | TFLint PR comment, Terraform plan comment, optional Infracost PR comment | Every pull request |
| `merge` | Deploy approved changes | Terraform apply (optional), cost diff JSONs, Slack alert on failure | After PR merge |
| `rollup`| Summarize costs across folders | Aggregated `infracost.rollup.json`, Slack success message | Nightly/weekly scheduled job |

---

## 🚀 Usage  

### 1. PR Mode (lint + plan + cost)  

```yaml
jobs:
  pr-checks:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v5
      - uses: faviaitsolutionsab/infra-boomer@v1
        with:
          mode: pr
          working_dir: examples/demo/terraform
          terraform_version: 1.13.1
          tflint_enable: true
          create_plan_comment: true
          infracost_enable: true        # Enable cost comments
          infracost_comment_title: "💸 PR cost impact"
          currency: USD
```

---

### 2. Merge Mode (apply only)  

_No cost, just Terraform apply._  

```yaml
jobs:
  merge-deploy:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v5
      - uses: faviaitsolutionsab/infra-boomer@v1
        with:
          mode: merge
          working_dir: examples/demo/terraform
          terraform_version: 1.13.1
          terraform_apply: true         # Apply on merge
          infracost_enable: false       # Skip cost
```

---

### 3. Merge Mode (apply + cost)  

_Run apply **and** record cost diff JSONs (recommended)._  

```yaml
jobs:
  merge-deploy:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v5
      - uses: faviaitsolutionsab/infra-boomer@v1
        with:
          mode: merge
          working_dir: examples/demo/terraform
          terraform_version: 1.13.1
          terraform_apply: true
          infracost_enable: true        # Enable cost diff
          currency: USD
          slack_error_notifications: true
          slack_bot_token: ${{ secrets.SLACK_BOT_TOKEN }}
          slack_channel_id: C12345678
```

This creates per-folder:  
- `.infracost-base.json`  
- `.infracost-new.json`  
- `infracost.out.json`  
- `infracost.rollup.json`  

---

### 4. Rollup Mode (aggregate costs)  

```yaml
jobs:
  rollup-costs:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v5
      - uses: faviaitsolutionsab/infra-boomer@v1
        with:
          mode: rollup
          rollup_input_dir: rollup
          currency: USD
          rollup_success_slack: true
          slack_bot_token: ${{ secrets.SLACK_BOT_TOKEN }}
          slack_channel_id: C12345678
```

---

## ⚙️ Inputs  

| Input | Default | Description |
|-------|---------|-------------|
| `mode` | `pr` | One of `pr`, `merge`, `rollup`. |
| `working_dir` | – | Terraform folder path. |
| `terraform_version` | `1.x` | Terraform version. |
| `terraform_apply` | `false` | If true in `merge` → runs `terraform apply`. |
| `tflint_enable` | `true` | Run TFLint. |
| `create_plan_comment` | `true` | Post PR plan summary. |
| `infracost_enable` | `true` | Enable Infracost (PR + merge). |
| `currency` | `USD` | Currency for cost estimates. |
| `slack_error_notifications` | `true` | Slack on failure (merge mode). |
| `rollup_success_slack` | `false` | Slack rollup success (rollup mode). |

---

## 🙌 Credits  

- Built with ❤️ on top of [Terraform](https://www.terraform.io/), [TFLint](https://github.com/terraform-linters/tflint), and [Infracost](https://www.infracost.io/).  
- License: [Apache 2.0](./LICENSE).  
- Please credit **infra-boomer** if you reuse or modify — it helps the community grow.  
