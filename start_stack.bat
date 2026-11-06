@echo off
title SentinelOps Stack Starter
echo ==========================================================
echo Starting SentinelOps Full Stack...
echo ==========================================================
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\start_stack.ps1"

