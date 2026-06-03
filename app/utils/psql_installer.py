import logging
import os
import platform
import sys
from pathlib import Path

logger = logging.getLogger("mxvault")


def ensure_psql_installed():
    """Install PostgreSQL client (psql) if not present. Runs at most once."""

    if os.system("which psql >/dev/null 2>&1") == 0:
        return

    sentinel = Path("/tmp/.mxvault_psql_installed")
    if sentinel.exists():
        logger.info("psql installation already attempted. Skipping.")
        return

    system = platform.system()
    logger.info(f"psql not found. Attempting installation on {system}...")

    try:
        if system == "Linux":
            _install_linux()
        elif system == "Darwin":
            _install_macos()
        elif system == "Windows":
            _install_windows()
        else:
            logger.warning(f"Unsupported platform: {system}. Install psql manually.")
    except Exception as exc:
        logger.error(f"Failed to install psql: {exc}")
    finally:
        sentinel.touch()


def _install_linux():
    if os.system("which apt >/dev/null 2>&1") == 0:
        logger.info("Installing PostgreSQL client via apt...")
        rc = os.system(
            "apt update -qq && apt install -y -qq curl ca-certificates gnupg lsb-release "
            "&& curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc "
            "| gpg --batch --dearmor -o /usr/share/keyrings/postgresql.gpg 2>/dev/null "
            '&& echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] '
            "https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main\" "
            "> /etc/apt/sources.list.d/pgdg.list "
            "&& apt update -qq && apt install -y -qq postgresql-client-18"
        )
        if rc == 0:
            logger.info("PostgreSQL client installed successfully via apt")
        else:
            logger.warning(f"apt installation failed (exit {rc})")
            _try_linux_fallback()
    elif os.system("which yum >/dev/null 2>&1") == 0:
        logger.info("Installing PostgreSQL client via yum...")
        rc = os.system("yum install -y -q postgresql")
        if rc == 0:
            logger.info("PostgreSQL client installed successfully via yum")
        else:
            logger.warning(f"yum installation failed (exit {rc})")
            _try_linux_fallback()
    elif os.system("which apk >/dev/null 2>&1") == 0:
        logger.info("Installing PostgreSQL client via apk...")
        rc = os.system("apk add --no-cache postgresql-client")
        if rc == 0:
            logger.info("PostgreSQL client installed successfully via apk")
        else:
            logger.warning(f"apk installation failed (exit {rc})")
    else:
        logger.warning("No supported package manager found (apt/yum/apk)")


def _try_linux_fallback():
    logger.info("Trying generic postgresql-client package...")
    rc = os.system("apt install -y -qq postgresql-client 2>/dev/null || "
                   "yum install -y -q postgresql 2>/dev/null || "
                   "apk add --no-cache postgresql-client 2>/dev/null")
    if rc == 0:
        logger.info("PostgreSQL client installed via fallback")
    else:
        logger.warning("All installation methods failed. Install psql manually.")


def _install_macos():
    if os.system("which brew >/dev/null 2>&1") == 0:
        logger.info("Installing PostgreSQL client via Homebrew...")
        rc = os.system("brew install libpq && brew link --force libpq")
        if rc == 0:
            logger.info("PostgreSQL client installed successfully via Homebrew")
        else:
            logger.warning(f"Homebrew installation failed (exit {rc})")

        if os.system("which psql >/dev/null 2>&1") != 0:
            psql_path = "/opt/homebrew/opt/libpq/bin/psql"
            if Path(psql_path).exists():
                logger.info(f"Linking {psql_path} manually...")
                os.system(
                    f"ln -sf {psql_path} /usr/local/bin/psql 2>/dev/null || "
                    f"ln -sf {psql_path} /opt/homebrew/bin/psql 2>/dev/null || true"
                )
                os.environ.setdefault("PATH", f"{os.environ.get('PATH', '')}:/opt/homebrew/opt/libpq/bin")
    else:
        logger.warning("Homebrew not found. Install PostgreSQL client manually:\n"
                       "  brew install libpq && brew link --force libpq")


def _install_windows():
    logger.info("Windows detected. Attempting PostgreSQL client installation...")

    if os.system("where choco >nul 2>&1") == 0:
        logger.info("Installing via Chocolatey...")
        rc = os.system("choco install postgresql --params '/NoServer' -y")
        if rc == 0:
            logger.info("PostgreSQL client installed successfully via Chocolatey")
            return
        logger.warning(f"Chocolatey installation failed (exit {rc})")

    if os.system("where winget >nul 2>&1") == 0:
        logger.info("Installing via winget...")
        rc = os.system("winget install -e --id PostgreSQL.PostgreSQL --silent 2>&1")
        if rc == 0:
            logger.info("PostgreSQL client installed successfully via winget")
            return
        logger.warning(f"winget installation failed (exit {rc})")

    logger.warning(
        "Could not install PostgreSQL client automatically.\n"
        "  Option 1: choco install postgresql --params '/NoServer'\n"
        "  Option 2: winget install -e --id PostgreSQL.PostgreSQL\n"
        "  Option 3: Download from https://www.postgresql.org/download/windows/"
    )
