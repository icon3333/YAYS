# YAYS

**Yet Another YouTube Summarizer**

AI-powered YouTube summaries delivered to your RSS reader. Self-hosted, privacy-first.

---

## What It Does

Monitor YouTube channels → Extract transcripts → Generate AI summaries → Email to your inbox or RSS reader

**Features:**
- 🤖 AI summaries using OpenAI (GPT-4o, GPT-4o-mini, o1-mini)
- 📧 Email delivery to inbox or RSS reader (Inoreader, The Old Reader, etc.)
- 📱 Web UI - Mobile-first interface
- 🔄 Auto-processing every 4 hours
- 💾 Import/Export - Backup your data
- 🚀 One-command install and update

**Cost:** ~$1-2/month for typical usage
**Setup:** One command. 2 minutes.

---

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/icon3333/YAYS/main/install.sh | bash
cd ~/YAYS
docker compose up -d
```

**Then open:** http://localhost:8015 and configure in the Settings tab.

**Time:** 2 minutes

---

## Update

```bash
cd ~/YAYS
./update.sh
```

That's it. The script handles everything:
- Pulls latest code
- Rebuilds containers
- Restarts services
- No manual steps needed

---

## Prerequisites

- Docker & Docker Compose ([get.docker.com](https://get.docker.com))
- OpenAI API key ([platform.openai.com/api-keys](https://platform.openai.com/api-keys))
- Target email (your inbox or RSS reader email)
- Gmail SMTP app password ([myaccount.google.com/security](https://myaccount.google.com/security))

---

## Usage

### Add Your First Channel

1. Open http://localhost:8015
2. Go to Settings tab
3. Configure API credentials
4. Paste YouTube channel URL
5. Click "Add Channel"

**Test channel:** `UCddiUEpeqJcYeBxX1IVBKvQ` (The Verge)

### Manual Processing

Don't wait for the 4-hour interval:

```bash
docker exec youtube-summarizer python process_videos.py
```

Watch logs:
```bash
docker compose logs -f
```

---

## Common Commands

```bash
# View logs
docker compose logs -f

# Restart (does NOT reload code, use ./update.sh instead)
docker compose restart

# Manual processing
docker exec youtube-summarizer python process_videos.py

# Check status
docker compose ps

# Stop
docker compose down
```

---

## Troubleshooting

### Containers Not Starting

```bash
cd ~/YAYS
./update.sh
```

### Port 8015 Already In Use

Edit `docker-compose.yml` line 17:
```yaml
ports:
  - "8080:8000"  # Change 8015 to your preferred port
```

Then:
```bash
docker compose down
docker compose up -d
```

### Check Logs for Errors

```bash
docker compose logs web
docker compose logs summarizer
```

---

## Remote Access

### Tailscale (Recommended)

```bash
# On server
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Access from anywhere
http://your-server-name:8015
```

**Why Tailscale:**
- No port forwarding needed
- End-to-end encrypted
- Works behind NAT
- Free for personal use

---

## Cost Analysis

**OpenAI Pricing:**

| Model | Per Video | Use Case |
|-------|-----------|----------|
| GPT-4o-mini | ~$0.001 | Cheapest, fast, good enough |
| GPT-4o | ~$0.015 | Better quality, 15x more expensive |
| o1-mini | ~$0.018 | Reasoning model, probably overkill |

**Monthly estimates (GPT-4o-mini):**
- 10 videos/day: ~$0.30
- 30 videos/day: ~$0.90
- 100 videos/day: ~$3.00

---

## Advanced

### Backup & Restore

Use the web UI Settings tab - has built-in backup/restore functionality.

### Cloud Deployment

Works on any server with Docker:
- AWS EC2
- DigitalOcean Droplet
- Raspberry Pi
- Home server

Just run the install command and access via Tailscale.

### Development

```bash
git clone https://github.com/icon3333/YAYS.git
cd YAYS
./deploy.sh  # Interactive setup for local development
```

---

## FAQ

**Q: Why email instead of direct RSS API?**
A: SMTP has worked since 1982. No OAuth, no webhooks, no PhD required.

**Q: Which OpenAI model?**
A: GPT-4o-mini for most people (fast, cheap, good).

**Q: Can I use without Docker?**
A: Yes, run `./deploy.sh` for local development. Docker is easier though.

**Q: What if transcript unavailable?**
A: Video gets skipped. Not all creators enable transcripts.

**Q: Remote access without port forwarding?**
A: Tailscale. Free, secure, zero-config VPN.

---

## Project Structure

```
YAYS/
├── src/                 # Python codebase
├── install.sh           # One-line installer
├── update.sh           # One-command updater
├── deploy.sh           # Local development setup
├── docker-compose.yml  # Container orchestration
├── config.txt          # Channels & settings (auto-created)
├── data/               # Database & state
└── logs/               # Application logs
```

---

## License

MIT License - See [LICENSE](LICENSE) file.

---

## Credits

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [OpenAI Python SDK](https://github.com/openai/openai-python) - API client
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Transcript extraction
- [Docker](https://www.docker.com/) - Containerization

---

**Built for self-hosters who value privacy, control, and efficiency.**

For issues or contributions, open a GitHub issue.
