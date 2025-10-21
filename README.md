# YAYS

**Yet Another YouTube Summarizer**

AI-powered YouTube summaries delivered to your RSS reader. Self-hosted, privacy-first.

---

## What It Does

Monitor YouTube channels → Extract transcripts → Generate AI summaries → Email to your inbox or RSS reader

**The pitch:** Watch 80% less, understand 100% more. Because life's too short for 40-minute videos that could've been a tweet.

**Features:**
- 🤖 **AI summaries** - OpenAI models (GPT-4o, GPT-4o-mini, o1-mini) - pick your speed/cost trade-off
- 📧 **Email delivery** - Send to your inbox or RSS reader (supports Inoreader, The Old Reader, etc.)
- 📱 **Web UI** - Mobile-first, because you're probably on the couch
- 🔄 **Auto-processing** - Set it, forget it, check every 4 hours
- 📊 **Time tracking** - See how many hours of your life you've saved
- 💾 **Import/Export** - Backup your data like a responsible adult
- 🔒 **Production-ready** - File locking, retry logic, health checks (we've been there)
- 🚀 **One-command deploy** - Because reading deployment docs is also a time sink

**Cost:** ~$1-2/month for typical usage. Cheaper than therapy for YouTube addiction.
**Setup:** One command. 2 minutes. Seriously.

---

## Install

### Docker (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/icon3333/YAYS/main/install.sh | bash
cd ~/YAYS
docker-compose up -d
```

**Default port:** 8000

**To change port:** Edit `docker-compose.yml` line 16: `"8000:8000"` → `"3000:8000"` (or your port), then `docker-compose restart`

**Then open:** http://localhost:8000 and configure in the Settings tab.

**Time:** 2 minutes

---

### Local Development

For development without Docker:

```bash
git clone https://github.com/icon3333/YAYS.git
cd YAYS
./deploy.sh  # Interactive setup
```

---

## Prerequisites

**What you need:**
- Docker & Docker Compose ([get.docker.com](https://get.docker.com))
- OpenAI API key ([platform.openai.com/api-keys](https://platform.openai.com/api-keys))
- Target email (where summaries are sent):
  - **Your inbox:** Use your regular email address
  - **RSS reader:** Use email-to-tag (e.g., Inoreader: `username.123456@inoreader.com`)
- Gmail SMTP (to send emails):
  - Gmail app password ([myaccount.google.com/security](https://myaccount.google.com/security) → App Passwords)

---

## Configuration

Configure everything in the **Settings tab** of the web UI (http://localhost:8000).

- **API Credentials:** OpenAI key, email settings
- **Video Processing:** Summary length, skip shorts, max videos per channel
- **Channels:** Add YouTube channels by channel ID or @handle

---

## Usage

### Access Web UI

- **Local:** http://localhost:8000
- **Tailscale:** http://your-server-name:8000

### Add Your First Channel

**Via Web UI (recommended):**
1. Open http://localhost:8000
2. Paste channel URL or ID
3. Click "Add Channel"

**Test channel:** `UCddiUEpeqJcYeBxX1IVBKvQ` (The Verge)

**Via config.txt:**
```bash
nano config.txt
# Add under [CHANNELS]:
# UCddiUEpeqJcYeBxX1IVBKvQ|The Verge
docker-compose restart summarizer
```

### Trigger Processing

Don't wait for 4-hour interval:

```bash
docker exec youtube-summarizer python process_videos.py
```

Watch logs:
```bash
docker-compose logs -f summarizer
```

Expected output:
```
Processing channel: The Verge
  ▶️  [Video Title]...
     ✅ Summary sent to RSS reader
```

Check your RSS reader inbox for email: `YAYS: [Video Title]`

---

## Common Commands

```bash
# View logs
docker-compose logs -f

# Restart services (does NOT reload code)
docker-compose restart

# Manual processing
docker exec youtube-summarizer python process_videos.py

# Check status
docker-compose ps

# Update from GitHub
git pull origin main
docker-compose up -d --build

# Backup (via web UI - Settings tab)
# Or manual file backup:
tar -czf backup.tar.gz config.txt data/

# Stop
docker-compose down
```

---

## Updates & Maintenance

### Update from GitHub

```bash
cd ~/YAYS
git pull origin main
docker-compose up -d --build
```

**What this does:**
1. Pulls latest code from GitHub
2. Rebuilds Docker images with new code
3. Restarts containers with updated code

**Note:** `docker-compose restart` does NOT reload code. You must use `--build` to pick up changes.

### Backup & Restore

**Via Web UI (easiest):**
1. Open http://localhost:8000
2. Go to Settings tab
3. Use "Backup & Restore" section

**Manual backup:**
```bash
cd ~/YAYS
# Backup data and config
tar -czf backup-$(date +%Y%m%d).tar.gz config.txt data/

# Restore
tar -xzf backup-20241020.tar.gz
docker-compose restart
```

---

## Remote Access

### Tailscale (Recommended)

```bash
# On server
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Access from anywhere
http://your-server-name:8000
```

**Why Tailscale:**
- No port forwarding
- End-to-end encrypted
- Works behind NAT
- Free for personal use

### Reverse Proxy (Advanced)

**Nginx + Let's Encrypt:**
```nginx
server {
    listen 80;
    server_name youtube.yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
sudo apt install nginx certbot python3-certbot-nginx
sudo ln -s /etc/nginx/sites-available/youtube-summarizer /etc/nginx/sites-enabled/
sudo certbot --nginx -d youtube.yourdomain.com
```

---

## Auto-Start on Boot

### Docker Restart Policy (Already Configured)
`docker-compose.yml` has `restart: always` - containers auto-start after reboot.

### Systemd Service (Optional)
```bash
./install-service.sh
```

**Manage:**
```bash
sudo systemctl status youtube-summarizer
sudo systemctl restart youtube-summarizer
sudo journalctl -u youtube-summarizer -f
```

---

## Features

| Feature | Description |
|---------|-------------|
| **AI Summaries** | Claude 3.5 Haiku - fast, accurate, ~$0.001/video |
| **Web UI** | Mobile-first interface - manage channels, view stats |
| **Auto-Processing** | Configurable interval (default: 4 hours) |
| **Smart Retry** | Exponential backoff for transient failures |
| **Time Tracking** | See exactly how much time you've saved |
| **Import/Export** | JSON/CSV backup, restore, migration |
| **Error Recovery** | Transcript fails → skip, AI fails → retry, email fails → queue |
| **Health Checks** | Docker health endpoints for monitoring |
| **Log Rotation** | Auto-cleanup, won't fill your disk |

---

## Why It's Different

Most YouTube summarizers are weekend projects that break on Monday. This one:

- **Actually works** - Dual transcript extraction (YouTube API + yt-dlp fallback) because APIs lie
- **Won't corrupt your data** - File-locked config prevents race conditions (learned the hard way)
- **Flexible delivery** - Email to your inbox or RSS reader (Inoreader, The Old Reader), not locked to one service
- **Production-grade** - Retry logic, error recovery, health checks, log rotation (the boring stuff that matters)
- **Respects your data** - Import/export everything, no vendor lock-in

---

## Import/Export

**Settings → Backup & Restore** in web UI:

| Export Type | Format | Use Case |
|-------------|--------|----------|
| **Feed Export** | JSON | Backup channels + videos with summaries |
| **Videos Export** | CSV | Analyze in Excel/Sheets (19 columns) |
| **Complete Backup** | JSON | Full config backup (no credentials) |

**Import:** Drag & drop JSON → Review preview → Import with conflict resolution

---

## Troubleshooting

### No Summaries Received

```bash
# Check for errors
docker-compose logs summarizer | grep ERROR

# Verify credentials
cat .env | grep -E "OPENAI|INOREADER|SMTP"

# Test manual processing
docker exec youtube-summarizer python process_videos.py
```

### Container Unhealthy

```bash
# View logs
docker logs youtube-summarizer
docker logs youtube-web

# Common fix
docker-compose down
docker-compose up -d
```

### Web UI Not Loading

```bash
# Check web container
docker-compose ps web

# Test health
curl http://localhost:8000/health

# Restart
docker-compose restart web
```

### Port 8000 In Use

Edit `docker-compose.yml`:
```yaml
ports:
  - "8001:8000"  # Change external port
```

Then:
```bash
docker-compose down
docker-compose up -d
```

### High Costs

Edit `config.txt`:
```ini
SUMMARY_LENGTH=300
SKIP_SHORTS=true
MAX_VIDEOS_PER_CHANNEL=3
```

---

## Advanced

### Multiple Instances

```bash
cp docker-compose.yml docker-compose-dev.yml
```

Edit `docker-compose-dev.yml`:
```yaml
ports:
  - "8001:8000"  # Different port
```

Start both:
```bash
docker-compose -f docker-compose.yml up -d
docker-compose -f docker-compose-dev.yml up -d
```

### Cloud Backup (rclone)

```bash
# Install
curl https://rclone.org/install.sh | sudo bash
rclone config

# Backup script
cat > cloud-backup.sh <<'EOF'
#!/bin/bash
tar -czf /tmp/yays-backup.tar.gz data/
rclone copy /tmp/yays-backup.tar.gz remote:yays-backups/
rm /tmp/yays-backup.tar.gz
EOF
chmod +x cloud-backup.sh

# Schedule daily
echo "0 3 * * * $PWD/cloud-backup.sh" | crontab -
```

### Monitoring

```bash
# Health check
curl http://localhost:8000/health

# Logs
docker-compose logs -f
docker-compose logs --tail 50 summarizer

# Resource usage
docker stats youtube-summarizer youtube-web

# Database stats
docker exec youtube-summarizer sqlite3 data/videos.db "
SELECT COUNT(*),
       SUM(duration_seconds) as total_seconds,
       ROUND(SUM(duration_seconds) * 0.8 / 3600.0, 1) as hours_saved
FROM videos;"
```

---

## Cost Analysis

**OpenAI Pricing (varies by model):**

| Model | Input | Output | Per Video | Use Case |
|-------|-------|--------|-----------|----------|
| GPT-4o-mini | $0.15/1M | $0.60/1M | ~$0.001 | Cheapest, fast, good enough |
| GPT-4o | $2.50/1M | $10.00/1M | ~$0.015 | Better quality, 15x more expensive |
| o1-mini | $3.00/1M | $12.00/1M | ~$0.018 | Reasoning model, probably overkill |

**Monthly estimates (GPT-4o-mini):**
- 10 videos/day: ~$0.30
- 30 videos/day: ~$0.90
- 100 videos/day: ~$3.00

**ROI:** 10+ hours/month saved via informed selection. Worth every penny.

---

## Security

- `.env` auto-set to 600 permissions
- Containers run as non-root
- No secrets in logs
- Resource limits prevent DoS
- Tailscale recommended (no port exposure)
- Backups excluded from git

---

## FAQ

**Q: Why email instead of direct RSS API?**
A: Because SMTP has worked since 1982 and doesn't require OAuth, webhooks, or a PhD. Fewer moving parts = fewer ways to break.

**Q: Which OpenAI model should I use?**
A: GPT-4o-mini for most people (fast, cheap, good). GPT-4o if you want better quality and don't mind 15x the cost. o1-mini is probably overkill for YouTube summaries.

**Q: Can I use without Docker?**
A: Sure, if you enjoy manually managing Python environments and systemd services. Docker handles isolation, health checks, and updates. Your call.

**Q: What if transcript unavailable?**
A: Video gets skipped and marked `failed_transcript`. Not all creators enable transcripts. Can't summarize what doesn't exist.

**Q: Multiple instances?**
A: Yes. Copy `docker-compose.yml`, change ports/names, use different `.env` files. Run as many as you want.

**Q: Remote access without port forwarding?**
A: Tailscale. Free, secure, zero-config VPN. Works behind NAT. Honestly magical.

---

## Project Structure

```
youtube-summarizer/
├── src/                        # Modular Python codebase
│   ├── core/                   # Processing logic (AI, transcript, email)
│   ├── managers/               # Config, database, settings
│   ├── web/                    # FastAPI application
│   └── static/                 # Frontend assets
├── install.sh                  # One-line curl installer
├── deploy.sh                   # Production deployment
├── process_videos.py           # Main processing loop
├── docker-compose.yml          # Orchestration
├── .env.example                # Environment template
├── config.txt                  # Channels & settings (auto-created)
├── data/                       # SQLite database & state
└── logs/                       # Application logs
```

---

## Development

### Running Locally (Without Docker)

For development or if you prefer running without Docker:

```bash
git clone https://github.com/icon3333/YAYS.git
cd YAYS
./deploy.sh  # Interactive credential setup
```

### Environment Variables (.env)

For local development, you can use `.env` file:

```bash
# Required
OPENAI_API_KEY=sk-...
TARGET_EMAIL=your-email@example.com
SMTP_USER=your.email@gmail.com
SMTP_PASS=your-app-password

# Optional
LOG_LEVEL=INFO
CHECK_INTERVAL_HOURS=4
```

**Note:** Docker users don't need `.env` - configure everything in the web UI Settings tab.

---

## License

MIT License - See [LICENSE](LICENSE) file.

---

## Credits

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [OpenAI Python SDK](https://github.com/openai/openai-python) - Claude API client
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Transcript fallback
- [Docker](https://www.docker.com/) - Containerization

---

**Built for self-hosters who value privacy, control, and efficiency.**

For issues or contributions, open a GitHub issue.
