#!/usr/bin/env python3
"""
Main entry point for RAG-powered FAQ Bot
Supports interactive chat and WhatsApp API modes
"""

import argparse
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()

async def run_interactive_chat():
    """Run interactive chat for testing"""
    from src.rag_faq_bot import RAGFAQBot
    
    print("="*60)
    print("🎓 University FAQ RAG Chatbot".center(60))
    print("="*60)
    print("\n🤖 Bot: Hello! Ask me about university admissions, fees, etc.")
    print("        Type 'exit' to quit or 'help' for examples.\n")
    
    # Initialize bot
    bot = RAGFAQBot(use_cache=True)
    
    while True:
        user_input = input("👤 You: ").strip()
        
        if not user_input:
            continue
        
        if user_input.lower() in ["exit", "quit", "bye"]:
            print("\n🤖 Bot: Goodbye! 👋\n")
            break
        
        if user_input.lower() == "help":
            print("\n🤖 Bot: Example questions:")
            print("   • When do admissions open?")
            print("   • What scholarships are available?")
            print("   • How do I apply for hostel?")
            print("   • What is the fee structure?\n")
            continue
        
        try:
            result = await bot.query(user_input, return_sources=True)
            response = result['response']
            
            print(f"\n🤖 Bot: [{response.intent}]")
            print(f"       {response.answer}\n")
            
        except Exception as e:
            print(f"\n🤖 Bot: Error: {str(e)}\n")

def run_whatsapp_server():
    """Run WhatsApp webhook server"""
    from api.whatsapp_webhook import app
    
    port = int(os.getenv('PORT', 5000))
    print(f"""
    ╔════════════════════════════════════════════╗
    ║   WhatsApp FAQ Bot Server                  ║
    ║   Running on http://localhost:{port}       ║
    ║   Webhook: http://localhost:{port}/webhook ║
    ╚════════════════════════════════════════════╝
    """)
    
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def initialize_vectorstore():
    """Initialize/rebuild vector store"""
    from src.rag_faq_bot import RAGFAQBot
    import shutil
    from pathlib import Path
    
    persist_dir = Path("./chroma_db")
    
    if persist_dir.exists():
        print("🗑️  Removing old vector store...")
        shutil.rmtree(persist_dir)
    
    print("🔄 Creating new vector store...")
    bot = RAGFAQBot(use_cache=False)
    print("✅ Vector store initialized!")

def show_analytics():
    """Show conversation analytics"""
    from src.conversation_logger import ConversationLogger
    import json
    
    logger = ConversationLogger()
    analytics = logger.get_analytics()
    
    print("\n📊 Conversation Analytics\n")
    print(json.dumps(analytics, indent=2))

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='University FAQ RAG Bot'
    )
    parser.add_argument(
        'mode',
        choices=['chat', 'whatsapp', 'init', 'analytics'],
        help='Mode: chat (interactive), whatsapp (server), init (setup), analytics (stats)'
    )
    
    args = parser.parse_args()
    
    if args.mode == 'chat':
        asyncio.run(run_interactive_chat())
    elif args.mode == 'whatsapp':
        run_whatsapp_server()
    elif args.mode == 'init':
        initialize_vectorstore()
    elif args.mode == 'analytics':
        show_analytics()

if __name__ == "__main__":
    main()
