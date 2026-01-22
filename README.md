# 📄 DocProcess API

A production-ready document processing service powered by [IBM's Docling](https://github.com/docling-project/docling). Convert PDFs, DOCX, and other documents into structured Markdown or JSON with AI-powered layout analysis and table extraction.

## ✨ Features

- **Multi-format Support**: PDF, DOCX, PPTX, HTML, and images
- **AI-Powered Extraction**: Layout analysis (DocLayNet) and table structure recognition (TableFormer)
- **OCR Support**: Process scanned documents with EasyOCR/RapidOCR
- **Multiple Output Formats**: Markdown, JSON, or both
- **Commercial-Ready**: API key authentication, credit-based billing, rate limiting
- **Database Persistence**: SQLAlchemy with SQLite/PostgreSQL for API keys and usage tracking
- **Stripe Integration**: Built-in payment processing for credit purchases
- **Flexible Deployment**: Lightning.AI, Modal, Docker, or self-hosted

## 🚀 Quick Start

### Option 1: Local Development with Docker

```bash
# Clone and setup
cd docling_as_api

# Start services (GPU)
./scripts/setup_local.sh

# Or for CPU-only
./scripts/setup_local.sh --cpu
```

### Option 2: Deploy to Lightning.AI (Recommended)

```bash
pip install lightning
./scripts/deploy_lightning.sh
```

### Option 3: Deploy to Modal

```bash
pip install modal
./scripts/deploy_modal.sh
```

## 📖 API Usage

### Create an API Key

```bash
curl -X POST http://localhost:8000/v1/keys \
  -H 'Content-Type: application/json' \
  -d '{"name": "My App", "credits": 1000}'
```

Response:
```json
{
  "id": "dk_abc123",
  "key": "dk_abc123_xyz789...",
  "name": "My App",
  "credits": 1000
}
```

> ⚠️ **Important**: Save your API key - it's only shown once!

### Convert a Document

```bash
curl -X POST http://localhost:8000/v1/convert/source \
  -H 'Authorization: Bearer YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
    "sources": [{"kind": "http", "url": "https://arxiv.org/pdf/2501.17887"}],
    "options": {"output_format": "markdown"}
  }'
```

### Upload a File

```bash
curl -X POST http://localhost:8000/v1/convert/file \
  -H 'Authorization: Bearer YOUR_API_KEY' \
  -F 'file=@document.pdf'
```

## 🐍 Python SDK

```python
from client import DocProcessClient

async def main():
    async with DocProcessClient(
        api_key="your-api-key",
        base_url="http://localhost:8000"
    ) as client:
        # Convert from URL
        result = await client.convert_url("https://example.com/doc.pdf")
        print(result.first_result.markdown)
        
        # Convert local file
        result = await client.convert_file("./document.pdf")
        
        # Check account
        info = await client.get_account_info()
        print(f"Credits remaining: {info.credits_remaining}")
```

Or use the sync client:

```python
from client.docling_client import DocProcessClientSync

client = DocProcessClientSync(api_key="your-key")
result = client.convert_url("https://example.com/doc.pdf")
print(result.first_result.markdown)
```

## 📁 Project Structure

```
docling_as_api/
├── api/                          # FastAPI wrapper service
│   ├── main.py                   # Application entry point
│   ├── config.py                 # Configuration management
│   ├── auth.py                   # API key authentication
│   ├── rate_limit.py             # Rate limiting
│   ├── models/                   # Pydantic schemas
│   ├── routes/                   # API endpoints
│   └── services/                 # Backend clients
│
├── client/                       # Python SDK
│   └── docling_client.py         # Async/sync client
│
├── deployments/
│   ├── lightning/                # Lightning.AI config
│   │   └── lightning.yaml
│   ├── modal/                    # Modal serverless
│   │   └── modal_docling.py
│   └── docker/                   # Self-hosted
│       ├── docker-compose.yml    # GPU config
│       ├── docker-compose.cpu.yml
│       ├── Dockerfile.api
│       └── nginx/
│
├── scripts/
│   ├── deploy_lightning.sh
│   ├── deploy_modal.sh
│   ├── setup_local.sh
│   └── test_api.py
│
├── requirements.txt
├── .env.example
└── README.md
```

## 🔧 Configuration

Copy `.env.example` to `.env` and configure:

```bash
# API Configuration
API_SECRET_KEY=your-secret-key  # Generate with: openssl rand -hex 32
API_DEBUG=false

# Docling Backend
DOCLING_BACKEND_URL=http://localhost:5001
DOCLING_TIMEOUT=300

# Rate Limiting
RATE_LIMIT_REQUESTS_PER_MINUTE=60

# Database (SQLite for dev, PostgreSQL for prod)
DATABASE_URL=sqlite:///./docprocess.db

# Redis (optional, for rate limiting)
REDIS_URL=redis://localhost:6379/0
```

## 📊 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/v1/convert/source` | POST | Convert from URL/base64 |
| `/v1/convert/file` | POST | Convert uploaded file |
| `/v1/convert/source/async` | POST | Async conversion |
| `/v1/status/{job_id}` | GET | Check async job status |
| `/v1/keys` | POST | Create API key |
| `/v1/keys/me` | GET | Get current key info |
| `/v1/usage/stats` | GET | Usage statistics |
| `/v1/usage/pricing` | GET | Pricing information |
| `/docs` | GET | Interactive API docs |

## 💰 Pricing Tiers

| Tier | Credits | Price | Per Document |
|------|---------|-------|--------------|
| Starter | 100 | $15 | $0.15 |
| Professional | 1,000 | $100 | $0.10 |
| Business | 5,000 | $400 | $0.08 |
| Enterprise | Custom | Contact | Volume pricing |

## 🏗️ Deployment Options

### Lightning.AI (Recommended for scale-to-zero)

Best for variable traffic with automatic scaling:

```yaml
# deployments/lightning/lightning.yaml
services:
  docling:
    image: quay.io/docling-project/docling-serve-cu128
    gpu: T4
    min_replicas: 0  # Scale to zero when idle
    max_replicas: 3
```

**Cost**: ~$0.50/hour when active, $0 when idle

### Modal (Serverless)

Best for pay-per-use with no infrastructure management:

```bash
modal deploy deployments/modal/modal_docling.py
```

**Cost**: ~$0.01-0.03 per document

### Docker Self-Hosted

Best for maximum control:

```bash
# GPU
docker compose -f deployments/docker/docker-compose.yml up -d

# CPU
docker compose -f deployments/docker/docker-compose.cpu.yml up -d
```

**Cost**: Depends on hosting provider ($30-400/month)

## 🔒 Security

- All endpoints require API key authentication
- Rate limiting per API key
- Request logging with correlation IDs
- HTTPS recommended for production (see nginx config)

## 🧪 Testing

```bash
# Run API tests
python scripts/test_api.py

# Or with custom URL
python scripts/test_api.py --url https://your-api.com --key YOUR_KEY
```

## 📈 Monitoring

- Health check: `GET /health`
- Readiness probe: `GET /ready`
- Liveness probe: `GET /live`
- Structured JSON logs with request IDs

## 🛠️ Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run API server (requires Docling backend)
uvicorn api.main:app --reload --port 8000
```

## 🐛 Troubleshooting

### GPU Not Detected

```bash
# Check NVIDIA drivers
nvidia-smi

# Check Docker GPU support
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

### Connection Timeout

- Increase `DOCLING_TIMEOUT` for large documents
- Use async endpoint for documents > 20 pages

### Out of Memory

- Reduce `DOCLING_SERVE_ENG_LOC_NUM_WORKERS`
- Use larger GPU instance

## 📚 Resources

- [Docling GitHub](https://github.com/docling-project/docling)
- [Docling-serve](https://github.com/docling-project/docling-serve)
- [GPU Documentation](https://docling-project.github.io/docling/usage/gpu/)
- [Lightning.AI](https://lightning.ai)
- [Modal](https://modal.com)

## 📄 License

MIT License - see LICENSE file for details.

---

Built with ❤️ using [Docling](https://github.com/docling-project/docling) by IBM Research
