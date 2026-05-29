# FargisGuard

FargisGuard is an AI-assisted trust & safety platform for Discord communities.

## Features

- AI-assisted moderation
- Warning escalation system
- Appeals workflow
- Human-supervised NSFW isolation
- Moderation logging
- FastAPI moderation dashboard
- Slash command administration
- Async OpenAI moderation pipeline

## Stack

- Python
- Discord.py
- OpenAI API
- FastAPI
- SQLite
- AWS EC2

## Architecture

FargisGuard uses:
- event-driven moderation
- async AI analysis
- human oversight for high-risk actions
- isolated NSFW moderation zones

## Deployment

Hosted on AWS EC2 with:
- systemd service management
- GitHub deployment workflow
- environment-based secrets
