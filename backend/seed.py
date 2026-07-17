from server import SessionLocal, ToolRegistry

def seed_db():
    db = SessionLocal()
    # Check if we already have it
    if not db.query(ToolRegistry).filter(ToolRegistry.url == "chatgpt.com").first():
        tool = ToolRegistry(url="chatgpt.com", status="approved", justification="Default enterprise approved AI tool.", clearance_level="PUBLIC")
        db.add(tool)
        db.commit()
        print("Database seeded with chatgpt.com (PUBLIC)")
        
    if not db.query(ToolRegistry).filter(ToolRegistry.url == "claude.ai").first():
        tool2 = ToolRegistry(url="claude.ai", status="approved", justification="For internal code analysis.", clearance_level="CONFIDENTIAL")
        db.add(tool2)
        db.commit()
        print("Database seeded with claude.ai (CONFIDENTIAL)")
    db.close()

if __name__ == "__main__":
    seed_db()
