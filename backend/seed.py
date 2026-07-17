from server import SessionLocal, ToolRegistry

def seed_db():
    db = SessionLocal()
    # Check if we already have it
    if not db.query(ToolRegistry).filter(ToolRegistry.url == "chatgpt.com").first():
        tool = ToolRegistry(url="chatgpt.com", status="approved", justification="Default enterprise approved AI tool.")
        db.add(tool)
        db.commit()
        print("Database seeded with chatgpt.com")
    else:
        print("Database already contains chatgpt.com")
    db.close()

if __name__ == "__main__":
    seed_db()
