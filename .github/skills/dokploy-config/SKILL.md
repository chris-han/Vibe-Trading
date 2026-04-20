---
name: dokploy-config
description: "Diagnose and update Dokploy compose deployments without keeping instance-specific throwaway scripts. Use when debugging Dokploy deployment state, environment config, generated compose output, shared Docker networks, or redeploy flows."
---

# Dokploy Config

## Purpose

Use this skill when a Dokploy deployment needs investigation or repair and the work should stay reusable instead of turning into one-off browser scripts.

## When to Use This Skill

- A Dokploy deployment is stuck, failing, or not creating containers
- You need to inspect Dokploy Environment, Deployments, or Containers state
- A compose deployment depends on shared Docker resources such as `dokploy-network`
- You need to confirm whether repo compose config is safe for Dokploy clones
- You are about to automate a Dokploy UI workflow and want to avoid hardcoded credentials, URLs, or service IDs

## Rules

- Do not store credentials in scripts, HTML dumps, or committed notes
- Do not hardcode deployment-specific URLs, service IDs, browser target IDs, or local absolute paths in reusable automation
- Prefer reusable parameters from env vars, CLI args, or user-provided values
- Prefer textual inspection and deterministic commands over screenshot dumps
- Remove transient screenshots, HTML captures, and probe scripts after the incident unless they were generalized first

## Standard Workflow

1. Confirm access path.
   Use the authenticated browser session on port `9222` for UI inspection, or SSH to the Dokploy host when the issue is host-side.

2. Check the three Dokploy views in order.
   Inspect `Environment`, then `Deployments`, then `Containers`.
   Look for missing env content, failed deployment logs, or zero running containers.

3. Check rendered compose assumptions.
   Compare the repo compose file with the generated Dokploy compose on the host.
   Watch for missing optional env files, external network references, and volume assumptions.

4. Check host prerequisites.
   Verify shared Docker resources required by Dokploy exist on the host, especially `dokploy-network`.

5. Redeploy with the narrowest safe action.
   Prefer a normal Dokploy redeploy from the correct branch.
   If UI automation is required, parameterize the target instead of embedding a single deployment URL.

6. Verify from inside out.
   Confirm container health on the host first, then check external reachability separately.
   Treat host health and public ingress as different failure domains.

## Reusable Patterns

- Compose fix: make repo env file usage tolerant of Dokploy fresh clones
- Host fix: create missing shared Docker network before retrying compose deployment
- Verification: capture a compact text summary of deployment status, container status, and health endpoint result
- Automation: wrap Dokploy base URL, project ID, environment ID, and service ID as inputs instead of constants

## Anti-Patterns

- Saving raw login pages or error pages as committed HTML snapshots
- Keeping iterative `v2`, `v3`, `final`, or `minimal` probe scripts after the incident
- Embedding secrets in browser automation
- Writing scripts tied to a single operator workstation path

## Deliverables

When the work is reusable, keep:

- A skill like this one
- Parameterized helpers only if they are generic and secret-free
- Brief notes on the root cause and verified fix

When the work is not reusable, keep only the conclusion and delete the ad hoc artifacts.