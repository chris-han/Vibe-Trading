# Dokploy Setup Guide

This document records all steps and configuration used to deploy the **semantier** project via Dokploy on the remote server.

---

## 1. Server Access

```bash
ssh -i KWECommonECS.pem root@47.113.199.183
```

- **User**: `root`
- **Host**: `47.113.199.183`
- **Key**: `KWECommonECS.pem`

---

## 2. Install Prerequisites

The Ubuntu apt mirrors (`mirrors.cloud.aliyuncs.com`) were timing out, so Node.js was installed from the official binary.

### 2.1 Install Node.js

```bash
curl -fsSL https://nodejs.org/dist/v20.19.0/node-v20.19.0-linux-x64.tar.xz -o /tmp/node-v20.19.0-linux-x64.tar.xz
tar -xf /tmp/node-v20.19.0-linux-x64.tar.xz -C /usr/local --strip-components=1
rm /tmp/node-v20.19.0-linux-x64.tar.xz
```

Verify:
```bash
node -v   # v20.19.0
npm -v    # 10.8.2
```

### 2.2 Install pnpm

```bash
npm install -g pnpm
pnpm -v   # 10.33.0
```

Configure global bin directory:
```bash
export PNPM_HOME=/root/.local/share/pnpm
export PATH=$PNPM_HOME:$PATH
mkdir -p $PNPM_HOME
```

Add to `~/.bashrc` for persistence:
```bash
echo 'export PNPM_HOME=/root/.local/share/pnpm' >> /root/.bashrc
echo 'export PATH=$PNPM_HOME:$PATH' >> /root/.bashrc
```

### 2.3 Install Dokploy CLI

```bash
pnpm add -g @dokploy/cli
dokploy --version   # 0.3.0
```

---

## 3. Authenticate with Dokploy

The Dokploy panel is running locally on the server at port `3000`.

Log in to your Dokploy dashboard.

Click on User icon in the sidebar.

Click on Profile.

Look for the API/CLI Section.

Click the Generate button to create your access token

```bash
dokploy auth -u http://localhost:3000 -t <ADMIN_API_TOKEN>
```

**Token used**:
```
lQLlyDxalPbBxVbhORBcPfBBnFqKqBCbKKVhmRGjizNArSRdsaufqMZrxhaaghNZ
```

> **Tip**: Generate a new token from the Dokploy dashboard if this one expires.

---

## 4. Add Local Server to Dokploy

On a fresh Dokploy install, no server is registered by default. The Dokploy container needs to SSH into the host to deploy.

### 4.1 Generate an SSH Key Pair

```bash
ssh-keygen -t ed25519 -f /root/.ssh/dokploy_local -N "" -C "dokploy@local"
cat /root/.ssh/dokploy_local.pub >> /root/.ssh/authorized_keys
```

### 4.2 Register the SSH Key in Dokploy

```bash
dokploy ssh-key create \
  --name local-key \
  --description "Local server SSH key" \
  --privateKey "$(cat /root/.ssh/dokploy_local)" \
  --publicKey "$(cat /root/.ssh/dokploy_local.pub)" \
  --organizationId kYQpOigDtAnqnsolHWhc_
```

**Key ID created**: `MDVVqXBGmbdW2ICLFPnBV`

### 4.3 Create the Server

Use the Docker bridge IP (`172.17.0.1`) so the Dokploy container can reach the host. Do **not** use `127.0.0.1` — from inside the container that points to itself.

```bash
dokploy server create \
  --name local \
  --description "Local Dokploy server" \
  --ipAddress 172.17.0.1 \
  --port 22 \
  --username root \
  --sshKeyId MDVVqXBGmbdW2ICLFPnBV \
  --serverType deploy
```

**Server ID created**: `szwrlJps44zaSLemkph7v`

---

## 5. Create the Project

```bash
dokploy project create \
  --name semantier \
  --description "Semantier project"
```

**IDs created**:
- **Project ID**: `IbXHYoPjNXkovej8h3MdN`
- **Environment ID** (auto-created): `wiHF2E2FUws51aOH7nJxl`

---

## 6. Configure Compose Service

### 6.1 Create the Compose

```bash
dokploy compose create \
  --name semantier \
  --environmentId wiHF2E2FUws51aOH7nJxl \
  --composeType docker-compose \
  --serverId szwrlJps44zaSLemkph7v \
  --composeFile "docker-compose.yml"
```

**Compose ID created**: `vpt7xRzSurBpsZD-DrcaF`

### 6.2 Update Git Source & Settings

```bash
dokploy compose update \
  --composeId vpt7xRzSurBpsZD-DrcaF \
  --sourceType git \
  --customGitUrl "https://github.com/chris-han/Vibe-Trading.git" \
  --customGitBranch main \
  --enableSubmodules \
  --composePath "./docker-compose.yml"
```

### 6.3 Deploy

```bash
dokploy compose deploy \
  --composeId vpt7xRzSurBpsZD-DrcaF \
  --title "Initial deployment" \
  --description "Deploy from main branch"
```

---

## 7. Verification

Check project status:
```bash
dokploy project all --json
```

Expected output:
- Project: `semantier`
- Environment: `production`
- Compose: `semantier` — Status: `running`

Check running containers:
```bash
docker ps
```

Expected:
```
vibe-trading   Up (healthy)   semantier:vibe-trading   0.0.0.0:8899->8899/tcp
```

---

## 8. Troubleshooting Notes

### 8.1 Apt mirrors timing out
The Alibaba Cloud mirrors (`mirrors.cloud.aliyuncs.com`) were unreachable. Node.js was installed directly from `nodejs.org` binaries instead of `apt`.

### 8.2 `ECONNREFUSED 127.0.0.1:22`
Dokploy runs inside a Docker container. When configured with `127.0.0.1`, it tries to SSH to **itself**, not the host. Always use the Docker bridge gateway IP:
```bash
ip addr show docker0 | grep "inet "
# 172.17.0.1
```

### 8.3 No server registered after fresh Dokploy install
If `dokploy server all --json` returns `[]`, you must manually:
1. Generate an SSH key pair
2. Add the public key to `~/.ssh/authorized_keys`
3. Register the key in Dokploy
4. Create the server with the bridge IP

---

## 9. Quick Reference Commands

| Action | Command |
|--------|---------|
| Login | `ssh -i KWECommonECS.pem root@47.113.199.183` |
| Auth CLI | `dokploy auth -u http://localhost:3000 -t <TOKEN>` |
| Deploy | `dokploy compose deploy --composeId vpt7xRzSurBpsZD-DrcaF --title "Update"` |
| View logs | `tail -f /etc/dokploy/logs/compose-navigate-online-protocol-ozfmgr/*.log` |
| Dashboard | `http://47.113.199.183:3000` |

---

## 10. Resource IDs

Keep these IDs for future CLI operations:

| Resource | ID |
|----------|-----|
| Organization | `kYQpOigDtAnqnsolHWhc_` |
| Project | `IbXHYoPjNXkovej8h3MdN` |
| Environment | `wiHF2E2FUws51aOH7nJxl` |
| Server | `szwrlJps44zaSLemkph7v` |
| Compose | `vpt7xRzSurBpsZD-DrcaF` |
| SSH Key | `MDVVqXBGmbdW2ICLFPnBV` |
