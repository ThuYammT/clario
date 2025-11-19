# **Clario — Odoo OCR Invoice Processing Addon**

Clario is a custom Odoo extension designed to simplify invoice and receipt management using OCR (Optical Character Recognition).  
It allows users to upload images/PDFs of invoices, extract key information using OCR + NLP, and automatically populate Odoo Accounting and Expenses modules.

This project is the Senior Project 2 (SP2) for **Assumption University**, built by a team of developers using Dockerized Odoo.

---

## 🚀 **Features**

### ✔️ Current
- Full Dockerized Odoo development environment  
- Custom OCR addon: `erp_ocr_addon`  
- Clean Git-ready project structure  
- Ready for team collaboration  

### ✔️ Planned Features
- Upload invoices & receipts (PDF, JPG, PNG)
- OCR extraction via Google Vision API or Tesseract
- NLP parsing for:
  - Vendor name  
  - Invoice number  
  - Date  
  - Total & VAT  
  - Line items (optional)
- Auto-create:
  - Vendor Bills in Accounting (`account.move`)
  - Expense records in HR Expenses (`hr.expense`)
- Editable preview screen
- Invoice analytics dashboard

---

# 🧱 **Tech Stack**

| Component | Technology |
|----------|------------|
| ERP Engine | Odoo 17 |
| OCR | Google Vision API / Tesseract |
| Backend | Python (Odoo ORM) |
| Database | PostgreSQL 15 |
| Environment | Docker & Docker Compose |
| UI | Odoo XML Views |
| Collaboration | GitHub |

---

# 📂 **Project Structure**

```
clario/
│
├── addons/
│   └── erp_ocr_addon/
│       ├── models/
│       ├── views/
│       ├── security/
│       ├── controllers/
│       ├── __manifest__.py
│       └── __init__.py
│
├── odoo-conf/
│   └── odoo.conf
│
├── docker-compose.yml
└── README.md
```

---

# 🐳 **Installation & Setup (For Team Members)**

Only **Docker Desktop** is required — no Odoo installation needed.

### **1. Clone the repository**

```bash
git clone https://github.com/ThuYammT/clario.git
cd clario
```

### **2. Start the system**

```bash
docker compose up -d
```

This will start:
- Odoo 17  
- PostgreSQL 15  
- Your custom addon volume  

### **3. Open Odoo**

Browser:

```
http://localhost:8069
```

Create a database:

- Name: `erp_ocr_dev`
- Email: any
- Password: any

### **4. Install the OCR Addon**

1. Go to **Apps**
2. Remove all filters  
3. Click **Update Apps List**
4. Search:

```
ERP OCR Addon
```

5. Install

---

# 🧑‍💻 **Developer Workflow**

### Restart after code changes:

```bash
docker compose restart odoo
```

### View logs:

```bash
docker compose logs -f odoo
```

### Stop services:

```bash
docker compose down
```

---

# 🤝 **Team Contribution Workflow (Git)**

### Pull latest before starting work:

```bash
git pull origin main
```

### Create a feature branch:

```bash
git checkout -b feature/ocr-upload
```

### Push your branch:

```bash
git push -u origin feature/ocr-upload
```

### Commit regularly:

```bash
git add .
git commit -m "Implemented OCR upload form"
git push
```

### Open a Pull Request → Review → Merge into main.

---

# 🛡️ **.gitignore Rules**

The following are excluded from GitHub:

```
db-data/
__pycache__/
*.log
*.pyc
*.pyo
.env
```

This prevents:
- Huge database files  
- Cache  
- Logs  
- Secrets  
from being uploaded.

---

# 🔮 **Future Enhancements**
- AI accuracy scoring  
- Thai OCR improvements  
- Auto-detect vendor based on past invoices  
- Fraud & risky invoice detection  
- LINE OA integration for mobile uploads  

---

# 👥 **Authors**

- Thu Ya Myint Myat Thein
- S Harry Lynn Oo
- Hein Htet Moe Tun

```bash
docker compose down
docker compose up -d
```

Or contact your team.

---

# 🎉 **Clario is ready for development!**
Next steps: create menus, upload form, OCR integration, NLP parsing, and accounting automation.

