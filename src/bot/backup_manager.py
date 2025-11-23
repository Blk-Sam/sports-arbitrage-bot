"""
Backup Manager - Automated backup system for arbitrage bot data

Handles:
- Automated backups on startup/shutdown
- Daily scheduled backups
- Backup rotation and cleanup
- Backup restoration
- Integrity verification
- Telegram notifications
"""

import os
import shutil
import tarfile
import json
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path


logger = logging.getLogger(__name__)


# Configuration
DATA_DIR = os.getenv("DASHBOARD_DATA_DIR", "data")
BACKUP_DIR = "backups"
LOGS_DIR = "logs"

# Retention policy (days)
RETENTION_RECENT = 7      # Keep daily backups for 7 days
RETENTION_MEDIUM = 30     # Keep weekly backups for 30 days
RETENTION_ARCHIVE = 90    # Keep monthly backups for 90 days

# Files to backup
FILES_TO_BACKUP = [
    os.path.join(DATA_DIR, "bet_history.csv"),
    os.path.join(DATA_DIR, "manual_pnl.csv"),
    os.path.join(DATA_DIR, "daily_pnl.csv"),
    os.path.join(DATA_DIR, "market_edge_summary.csv"),
    "scheduling/scheduler.db",
    "config/.env"
]


class BackupManager:
    """Manage backups with automated rotation and cleanup."""
    
    def __init__(self):
        """Initialize backup manager."""
        self.backup_dir = BACKUP_DIR
        self.ensure_backup_dir()
    
    def ensure_backup_dir(self) -> None:
        """Create backup directory if it doesn't exist."""
        os.makedirs(self.backup_dir, exist_ok=True)
        logger.debug(f"Backup directory ensured: {self.backup_dir}")
    
    def get_today_backup_dir(self) -> str:
        """Get or create today's backup subdirectory."""
        today = datetime.now().strftime("%Y-%m-%d")
        today_dir = os.path.join(self.backup_dir, today)
        os.makedirs(today_dir, exist_ok=True)
        return today_dir
    
    def create_backup(self, backup_type: str = "manual") -> Optional[str]:
        """
        Create a backup of critical files.
        
        Args:
            backup_type: 'manual', 'startup', 'shutdown', 'daily', 'scheduled'
            
        Returns:
            Path to backup file if successful, None otherwise
        """
        try:
            today_dir = self.get_today_backup_dir()
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            backup_name = f"backup_{timestamp}_{backup_type}.tar.gz"
            backup_path = os.path.join(today_dir, backup_name)
            
            logger.info(f"🔄 Creating {backup_type} backup: {backup_path}")
            
            # Collect existing files
            files_to_compress = []
            for file_path in FILES_TO_BACKUP:
                if os.path.exists(file_path):
                    files_to_compress.append(file_path)
                    logger.debug(f"   Added to backup: {file_path}")
                else:
                    logger.warning(f"   File not found (skipping): {file_path}")
            
            if not files_to_compress:
                logger.error("❌ No files found to backup")
                return None
            
            # Create tar.gz archive
            with tarfile.open(backup_path, "w:gz") as tar:
                for file_path in files_to_compress:
                    arcname = file_path.replace(os.sep, "/")
                    tar.add(file_path, arcname=arcname)
            
            # Calculate checksum
            checksum = self.calculate_checksum(backup_path)
            
            # Create manifest
            manifest = {
                "timestamp": timestamp,
                "backup_type": backup_type,
                "backup_file": backup_name,
                "checksum": checksum,
                "files_count": len(files_to_compress),
                "size_bytes": os.path.getsize(backup_path),
                "size_mb": round(os.path.getsize(backup_path) / (1024 * 1024), 2)
            }
            
            manifest_path = os.path.join(today_dir, f"manifest_{timestamp}.json")
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)
            
            logger.info(f"✅ Backup created successfully")
            logger.info(f"   Path: {backup_path}")
            logger.info(f"   Size: {manifest['size_mb']} MB")
            logger.info(f"   Checksum: {checksum[:16]}...")
            
            return backup_path
        
        except Exception as e:
            logger.error(f"❌ Error creating backup: {e}", exc_info=True)
            return None
    
    def calculate_checksum(self, file_path: str) -> str:
        """Calculate SHA256 checksum of file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def verify_backup(self, backup_path: str, expected_checksum: str) -> bool:
        """
        Verify backup integrity.
        
        Args:
            backup_path: Path to backup file
            expected_checksum: Expected SHA256 hash
            
        Returns:
            True if checksum matches, False otherwise
        """
        try:
            actual_checksum = self.calculate_checksum(backup_path)
            is_valid = actual_checksum == expected_checksum
            
            if is_valid:
                logger.info(f"✅ Backup verification passed: {backup_path}")
            else:
                logger.error(f"❌ Backup verification failed: {backup_path}")
                logger.error(f"   Expected: {expected_checksum}")
                logger.error(f"   Actual: {actual_checksum}")
            
            return is_valid
        
        except Exception as e:
            logger.error(f"❌ Error verifying backup: {e}")
            return False
    
    def restore_backup(self, backup_path: str) -> bool:
        """
        Restore from backup.
        
        Args:
            backup_path: Path to backup file
            
        Returns:
            True if restore successful, False otherwise
        """
        try:
            logger.info(f"🔄 Restoring from backup: {backup_path}")
            
            if not os.path.exists(backup_path):
                logger.error(f"❌ Backup file not found: {backup_path}")
                return False
            
            # Extract archive
            with tarfile.open(backup_path, "r:gz") as tar:
                tar.extractall(path=".")
            
            logger.info(f"✅ Backup restored successfully")
            return True
        
        except Exception as e:
            logger.error(f"❌ Error restoring backup: {e}", exc_info=True)
            return False
    
    def get_backup_list(self) -> List[Dict[str, Any]]:
        """
        Get list of all available backups.
        
        Returns:
            List of backup information dictionaries
        """
        backups = []
        
        try:
            for date_dir in sorted(os.listdir(self.backup_dir), reverse=True):
                date_path = os.path.join(self.backup_dir, date_dir)
                
                if not os.path.isdir(date_path):
                    continue
                
                for file_name in sorted(os.listdir(date_path), reverse=True):
                    if file_name.endswith(".tar.gz"):
                        file_path = os.path.join(date_path, file_name)
                        
                        # Try to read manifest
                        manifest_file = file_name.replace(".tar.gz", "")
                        manifest_path = os.path.join(date_path, f"manifest_{manifest_file.replace('backup_', '')}.json")
                        
                        manifest_data = {}
                        if os.path.exists(manifest_path):
                            try:
                                with open(manifest_path, "r") as f:
                                    manifest_data = json.load(f)
                            except:
                                pass
                        
                        backups.append({
                            "file_name": file_name,
                            "file_path": file_path,
                            "date": date_dir,
                            "size_mb": round(os.path.getsize(file_path) / (1024 * 1024), 2),
                            "type": manifest_data.get("backup_type", "unknown"),
                            "checksum": manifest_data.get("checksum", "N/A"),
                            "created_at": manifest_data.get("timestamp", "N/A")
                        })
        
        except Exception as e:
            logger.error(f"❌ Error listing backups: {e}")
        
        return backups
    
    def cleanup_old_backups(self) -> Dict[str, int]:
        """
        Clean up old backups based on retention policy.
        
        Returns:
            Dictionary with cleanup statistics
        """
        logger.info("🧹 Starting backup cleanup...")
        
        stats = {
            "total_before": 0,
            "deleted": 0,
            "kept_recent": 0,
            "kept_medium": 0,
            "kept_archive": 0,
            "freed_mb": 0
        }
        
        try:
            backups = self.get_backup_list()
            stats["total_before"] = len(backups)
            
            now = datetime.now()
            
            for backup in backups:
                try:
                    backup_date = datetime.strptime(backup["date"], "%Y-%m-%d")
                    days_old = (now - backup_date).days
                    file_path = backup["file_path"]
                    file_size_mb = backup["size_mb"]
                    
                    # Determine retention policy
                    should_keep = False
                    
                    if days_old <= RETENTION_RECENT:
                        # Keep all recent backups
                        should_keep = True
                        stats["kept_recent"] += 1
                    elif days_old <= RETENTION_MEDIUM:
                        # Keep weekly (every 7 days)
                        if days_old % 7 == 0 or backup_date.weekday() == 0:  # Monday
                            should_keep = True
                            stats["kept_medium"] += 1
                    elif days_old <= RETENTION_ARCHIVE:
                        # Keep monthly (1st of each month)
                        if backup_date.day == 1:
                            should_keep = True
                            stats["kept_archive"] += 1
                    
                    if not should_keep:
                        os.remove(file_path)
                        logger.debug(f"   Deleted: {backup['file_name']} ({file_size_mb} MB)")
                        stats["deleted"] += 1
                        stats["freed_mb"] += file_size_mb
                
                except Exception as e:
                    logger.warning(f"   Error processing backup {backup['file_name']}: {e}")
            
            # Clean up empty date directories
            for date_dir in os.listdir(self.backup_dir):
                date_path = os.path.join(self.backup_dir, date_dir)
                if os.path.isdir(date_path) and not os.listdir(date_path):
                    os.rmdir(date_path)
                    logger.debug(f"   Deleted empty directory: {date_dir}")
            
            logger.info(f"✅ Cleanup complete")
            logger.info(f"   Total backups before: {stats['total_before']}")
            logger.info(f"   Deleted: {stats['deleted']}")
            logger.info(f"   Kept (recent): {stats['kept_recent']}")
            logger.info(f"   Kept (medium): {stats['kept_medium']}")
            logger.info(f"   Kept (archive): {stats['kept_archive']}")
            logger.info(f"   Freed space: {stats['freed_mb']} MB")
            
            return stats
        
        except Exception as e:
            logger.error(f"❌ Error cleaning up backups: {e}", exc_info=True)
            return stats
    
    def get_backup_stats(self) -> Dict[str, Any]:
        """
        Get backup statistics and storage usage.
        
        Returns:
            Dictionary with backup statistics
        """
        try:
            backups = self.get_backup_list()
            
            total_size = sum(b["size_mb"] for b in backups)
            total_size_gb = round(total_size / 1024, 2)
            
            by_type = {}
            for backup in backups:
                backup_type = backup["type"]
                if backup_type not in by_type:
                    by_type[backup_type] = {"count": 0, "size_mb": 0}
                by_type[backup_type]["count"] += 1
                by_type[backup_type]["size_mb"] += backup["size_mb"]
            
            return {
                "total_backups": len(backups),
                "total_size_mb": round(total_size, 2),
                "total_size_gb": total_size_gb,
                "by_type": by_type,
                "oldest_backup": backups[-1]["created_at"] if backups else None,
                "newest_backup": backups[0]["created_at"] if backups else None
            }
        
        except Exception as e:
            logger.error(f"❌ Error getting backup stats: {e}")
            return {}


# Convenience functions
_backup_manager = None

def get_backup_manager() -> BackupManager:
    """Get or create backup manager singleton."""
    global _backup_manager
    if _backup_manager is None:
        _backup_manager = BackupManager()
    return _backup_manager


def backup_on_startup() -> Optional[str]:
    """Create backup on bot startup."""
    return get_backup_manager().create_backup("startup")


def backup_on_shutdown() -> Optional[str]:
    """Create backup on bot shutdown."""
    return get_backup_manager().create_backup("shutdown")


def backup_daily() -> Optional[str]:
    """Create daily backup."""
    return get_backup_manager().create_backup("daily")


def backup_manual() -> Optional[str]:
    """Create manual backup."""
    return get_backup_manager().create_backup("manual")


if __name__ == "__main__":
    import sys
    
    manager = BackupManager()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "create":
            backup_type = sys.argv[2] if len(sys.argv) > 2 else "manual"
            path = manager.create_backup(backup_type)
            if path:
                print(f"✅ Backup created: {path}")
            else:
                print("❌ Backup failed")
                sys.exit(1)
        
        elif command == "restore":
            if len(sys.argv) < 3:
                print("Usage: python backup_manager.py restore <backup_file>")
                sys.exit(1)
            backup_file = sys.argv[2]
            if manager.restore_backup(backup_file):
                print("✅ Backup restored")
            else:
                print("❌ Restore failed")
                sys.exit(1)
        
        elif command == "list":
            backups = manager.get_backup_list()
            print(f"\n📋 Available Backups ({len(backups)} total):\n")
            for i, backup in enumerate(backups, 1):
                print(f"{i}. {backup['file_name']}")
                print(f"   Date: {backup['date']}")
                print(f"   Type: {backup['type']}")
                print(f"   Size: {backup['size_mb']} MB")
                print(f"   Checksum: {backup['checksum'][:16]}...")
                print()
        
        elif command == "cleanup":
            stats = manager.cleanup_old_backups()
            print(f"✅ Cleanup complete: {stats['deleted']} backups deleted, {stats['freed_mb']} MB freed")
        
        elif command == "stats":
            stats = manager.get_backup_stats()
            print(f"\n📊 Backup Statistics:\n")
            print(f"Total backups: {stats.get('total_backups', 0)}")
            print(f"Total size: {stats.get('total_size_gb', 0)} GB ({stats.get('total_size_mb', 0)} MB)")
            print(f"Oldest backup: {stats.get('oldest_backup', 'N/A')}")
            print(f"Newest backup: {stats.get('newest_backup', 'N/A')}")
            print(f"\nBy type:")
            for backup_type, data in stats.get("by_type", {}).items():
                print(f"  {backup_type}: {data['count']} backups, {data['size_mb']} MB")
    else:
        print("Usage:")
        print("  python backup_manager.py create [backup_type]")
        print("  python backup_manager.py restore <backup_file>")
        print("  python backup_manager.py list")
        print("  python backup_manager.py cleanup")
        print("  python backup_manager.py stats")
