"""
Dashboard Backup Panel - Streamlit UI for backup management

Provides:
- Manual backup creation
- Backup list and restore
- Storage statistics
- Backup verification
"""

import streamlit as st
import os
import sys
from datetime import datetime
from src.bot.backup_manager import (
    BackupManager,
    get_backup_manager
)


def render_backup_panel():
    """Render complete backup management panel."""
    
    st.header("💾 Backup Management")
    st.markdown("Manage your arbitrage bot backups and data recovery")
    
    # Get backup manager
    manager = get_backup_manager()
    
    # Main tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📦 Create Backup",
        "📋 Backup List",
        "📊 Statistics",
        "⚙️ Settings"
    ])
    
    # === TAB 1: CREATE BACKUP ===
    with tab1:
        st.subheader("Create New Backup")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🚀 Quick Backup", use_container_width=True):
                with st.spinner("Creating backup..."):
                    backup_path = manager.create_backup("manual")
                    if backup_path:
                        st.success(f"✅ Backup created successfully!")
                        st.info(f"📁 Location: `{backup_path}`")
                    else:
                        st.error("❌ Failed to create backup")
        
        with col2:
            if st.button("🔄 Full Backup", use_container_width=True):
                with st.spinner("Creating full backup..."):
                    # Clean up old backups first
                    cleanup_stats = manager.cleanup_old_backups()
                    st.info(f"Cleanup: Freed {cleanup_stats['freed_mb']} MB")
                    
                    # Create new backup
                    backup_path = manager.create_backup("manual")
                    if backup_path:
                        st.success(f"✅ Full backup created!")
                        st.info(f"📁 Location: `{backup_path}`")
                    else:
                        st.error("❌ Failed to create backup")
        
        with col3:
            backup_type = st.selectbox(
                "Backup Type",
                ["manual", "startup", "shutdown", "daily"],
                label_visibility="collapsed"
            )
            if st.button("📌 Custom Backup", use_container_width=True):
                with st.spinner(f"Creating {backup_type} backup..."):
                    backup_path = manager.create_backup(backup_type)
                    if backup_path:
                        st.success(f"✅ {backup_type.title()} backup created!")
                    else:
                        st.error("❌ Failed to create backup")
        
        st.markdown("---")
        
        st.subheader("ℹ️ What Gets Backed Up")
        st.markdown("""
        **Critical Files:**
        - 📊 `data/bet_history.csv` - Your trading history
        - 💼 `data/manual_pnl.csv` - Manual trading records
        - 📈 `data/daily_pnl.csv` - Daily summaries
        - 📉 `data/market_edge_summary.csv` - Market analytics
        - 🗄️ `scheduling/scheduler.db` - Event database
        - ⚙️ `config/.env` - Configuration settings
        
        **Format:** Compressed .tar.gz archive with integrity checksums
        **Retention:** 7 days daily, 30 days weekly, 90 days monthly
        """)
    
    # === TAB 2: BACKUP LIST ===
    with tab2:
        st.subheader("Available Backups")
        
        # Refresh button
        if st.button("🔄 Refresh Backup List", use_container_width=True):
            st.rerun()
        
        backups = manager.get_backup_list()
        
        if not backups:
            st.info("ℹ️ No backups found. Create your first backup above!")
        else:
            st.success(f"✅ Found {len(backups)} backup(s)")
            st.markdown("---")
            
            # Display backups
            for i, backup in enumerate(backups):
                with st.expander(
                    f"📦 {backup['file_name']} ({backup['size_mb']} MB) - {backup['date']}",
                    expanded=False
                ):
                    col1, col2, col3 = st.columns([2, 1, 1])
                    
                    with col1:
                        st.write(f"**Type:** {backup['type']}")
                        st.write(f"**Created:** {backup['created_at']}")
                        st.write(f"**Size:** {backup['size_mb']} MB")
                        st.write(f"**Checksum:** `{backup['checksum'][:16]}...`")
                    
                    with col2:
                        if st.button("📥 Restore", key=f"restore_{i}", use_container_width=True):
                            with st.spinner("Restoring backup..."):
                                if manager.restore_backup(backup['file_path']):
                                    st.success("✅ Backup restored successfully!")
                                    st.warning("⚠️ Please restart the bot to apply changes")
                                else:
                                    st.error("❌ Restore failed")
                    
                    with col3:
                        if st.button("🗑️ Delete", key=f"delete_{i}", use_container_width=True):
                            try:
                                os.remove(backup['file_path'])
                                st.success("✅ Backup deleted")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error deleting backup: {e}")
    
    # === TAB 3: STATISTICS ===
    with tab3:
        st.subheader("Backup Statistics")
        
        stats = manager.get_backup_stats()
        
        if stats:
            # Main metrics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "📦 Total Backups",
                    stats.get('total_backups', 0)
                )
            
            with col2:
                st.metric(
                    "💾 Total Storage",
                    f"{stats.get('total_size_gb', 0)} GB"
                )
            
            with col3:
                st.metric(
                    "📊 Storage (MB)",
                    f"{stats.get('total_size_mb', 0)} MB"
                )
            
            with col4:
                max_size = 90 * 200  # Estimate ~200MB per day for 90 days
                current_size = stats.get('total_size_mb', 0)
                usage_pct = (current_size / max_size * 100) if max_size > 0 else 0
                st.metric(
                    "📈 Storage Usage",
                    f"{round(usage_pct, 1)}%"
                )
            
            st.markdown("---")
            
            # By backup type
            by_type = stats.get('by_type', {})
            if by_type:
                st.subheader("Backups by Type")
                
                for backup_type, data in by_type.items():
                    col1, col2, col3 = st.columns([2, 1, 1])
                    with col1:
                        st.write(f"**{backup_type.title()}**")
                    with col2:
                        st.write(f"{data['count']} backups")
                    with col3:
                        st.write(f"{round(data['size_mb'], 2)} MB")
            
            st.markdown("---")
            
            # Timeline
            st.subheader("Backup Timeline")
            st.write(f"**Oldest:** {stats.get('oldest_backup', 'N/A')}")
            st.write(f"**Newest:** {stats.get('newest_backup', 'N/A')}")
        else:
            st.info("ℹ️ No backup statistics available")
    
    # === TAB 4: SETTINGS ===
    with tab4:
        st.subheader("Backup Settings")
        
        st.info("⚙️ Retention Policy Configuration")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "Recent Backups",
                "7 days",
                "Keep all daily"
            )
        
        with col2:
            st.metric(
                "Medium Backups",
                "30 days",
                "Keep weekly"
            )
        
        with col3:
            st.metric(
                "Archive Backups",
                "90 days",
                "Keep monthly"
            )
        
        st.markdown("---")
        
        st.subheader("🧹 Cleanup Options")
        
        if st.button("Clean Up Old Backups", use_container_width=True):
            with st.spinner("Cleaning up old backups..."):
                stats = manager.cleanup_old_backups()
                st.success(f"✅ Cleanup complete!")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Deleted", stats['deleted'])
                with col2:
                    st.metric("Freed (MB)", round(stats['freed_mb'], 2))
                with col3:
                    st.metric("Kept", stats['total_before'] - stats['deleted'])
        
        st.markdown("---")
        
        st.subheader("📋 Retention Policy Info")
        
        st.markdown("""
        **How retention works:**
        
        1. **Recent (0-7 days)**
           - Keep ALL daily backups
           - Quick recovery from recent changes
        
        2. **Medium (8-30 days)**
           - Keep weekly backups (Mondays)
           - Balance between retention and storage
        
        3. **Archive (31-90 days)**
           - Keep monthly backups (1st of month)
           - Long-term data preservation
        
        4. **Deleted (90+ days)**
           - Automatically removed
           - Saves storage space
        
        **Storage Estimate:**
        - ~200-300 MB per day
        - ~90 days retention = ~20-30 GB
        - Highly compressed and optimized
        """)


# When called from dashboard
if __name__ == "__main__":
    st.set_page_config(page_title="Backup Manager", page_icon="💾", layout="wide")
    render_backup_panel()
