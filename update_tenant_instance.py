#!/usr/bin/env python3
"""
Script to update tenant WhatsApp instance ID to match the real Evolution API instance
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update
import os
from app.models.tenant.tenant import Tenant

async def update_tenant_whatsapp_instance():
    # Use the same database URL as the Docker container
    DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/agenda"
    
    # Create async engine
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Find our test tenant
        result = await session.execute(
            select(Tenant).where(Tenant.name == "KIBO Test Clinic")
        )
        tenant = result.scalar_one_or_none()
        
        if tenant:
            old_instance = tenant.whatsapp_instance_id
            # Update to the real Evolution API instance name
            tenant.whatsapp_instance_id = "bf8738e1-d28b-45d1-a710-2845403b538a"
            
            await session.commit()
            await session.refresh(tenant)
            
            print(f"✅ Updated tenant WhatsApp instance:")
            print(f"   Old: {old_instance}")
            print(f"   New: {tenant.whatsapp_instance_id}")
        else:
            print("❌ Test tenant 'KIBO Test Clinic' not found")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(update_tenant_whatsapp_instance())