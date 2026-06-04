from flask import Flask, request, jsonify, Response
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os
import asyncio
import concurrent.futures
from dotenv import load_dotenv

from src.rag_faq_bot import RAGFAQBot
from src.conversation_logger import ConversationLogger

load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Initialize Twilio
twilio_client = Client(
    os.getenv('TWILIO_ACCOUNT_SID'),
    os.getenv('TWILIO_AUTH_TOKEN')
)

# Initialize RAG bot (singleton)
rag_bot = None
logger = ConversationLogger()

def get_rag_bot():
    """Get or initialize RAG bot"""
    global rag_bot
    if rag_bot is None:
        print("🤖 Initializing RAG FAQ Bot...")
        rag_bot = RAGFAQBot(
            csv_path=os.getenv('CSV_PATH', 'data/synthetic_faq_dataset.csv'),
            use_cache=True
        )
        print("✅ RAG Bot Ready!")
    return rag_bot

def run_async_query(bot, question):
    """Helper to run async query in sync context"""
    try:
        # Try to get existing event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is running, use asyncio.run in a thread
            def run_in_thread():
                # Create new event loop in thread
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(bot.query(question, return_sources=True))
                finally:
                    new_loop.close()
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                return future.result()
        else:
            return loop.run_until_complete(bot.query(question, return_sources=True))
    except RuntimeError:
        # No event loop exists, create new one
        return asyncio.run(bot.query(question, return_sources=True))

@app.route('/')
def home():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "University FAQ WhatsApp Bot",
        "version": "1.0.0"
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Main WhatsApp webhook endpoint
    Receives messages from Twilio and sends responses
    """
    try:
        # Get message details
        incoming_msg = request.values.get('Body', '').strip()
        from_number = request.values.get('From', '')
        user_id = from_number.replace('whatsapp:', '')
        
        print(f"📩 Received from {user_id}: {incoming_msg}")
        
        # Handle empty messages
        if not incoming_msg:
            return respond_whatsapp("Please send a valid question!")
        
        # Handle special commands
        if incoming_msg.lower() in ['hi', 'hello', 'hey']:
            welcome_msg = (
                "👋 *Welcome to University FAQ Bot!*\n\n"
                "I can help you with:\n"
                "• Admission dates & deadlines\n"
                "• Fee structure & scholarships\n"
                "• Hostel & transport info\n"
                "• Departments & programs\n"
                "• And much more!\n\n"
                "Ask me anything about the university!"
            )
            return respond_whatsapp(welcome_msg)
        
        if incoming_msg.lower() == 'help':
            help_msg = (
                "📚 *Example Questions:*\n\n"
                "• When do admissions open?\n"
                "• What scholarships are available?\n"
                "• How do I apply for hostel?\n"
                "• What is the fee structure?\n"
                "• Contact information?\n\n"
                "Type 'menu' to see all topics."
            )
            return respond_whatsapp(help_msg)
        
        if incoming_msg.lower() == 'menu':
            bot = get_rag_bot()
            intents = bot.get_all_intents()
            menu_msg = "*📋 Available Topics:*\n\n"
            for i, intent in enumerate(intents, 1):
                menu_msg += f"{i}. {intent.replace('_', ' ')}\n"
            menu_msg += "\nAsk me about any topic!"
            return respond_whatsapp(menu_msg)
        
        # Get RAG response
        bot = get_rag_bot()
        result = run_async_query(bot, incoming_msg)
        
        # Validate result structure
        if not result or 'response' not in result:
            raise ValueError("Invalid response structure from RAG bot")
        
        # Format response for WhatsApp
        response_text = format_whatsapp_response(result)
        
        # Log conversation
        logger.log_interaction(
            question=incoming_msg,
            intent=result['response'].intent,
            confidence=1.0,  # You can add confidence scoring if needed
            user_id=user_id,
            response=response_text
        )
        
        print(f"💬 Sending response: {response_text[:100]}...")
        
        return respond_whatsapp(response_text)
    
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        error_msg = (
            "Sorry, I encountered an error. 😔\n\n"
            "Please try:\n"
            "• Rephrasing your question\n"
            "• Typing 'help' for examples\n"
            "• Contacting: admission@university.edu"
        )
        return respond_whatsapp(error_msg)

def respond_whatsapp(message):
    """
    Create Twilio WhatsApp response
    
    Args:
        message (str): Message to send
        
    Returns:
        Response: Flask response with TwiML XML content
    """
    resp = MessagingResponse()
    resp.message(message)
    return Response(str(resp), mimetype='application/xml')

def format_whatsapp_response(result):
    """
    Format RAG response for WhatsApp with emojis and structure
    
    Args:
        result (dict): RAG query result with response and sources
        
    Returns:
        str: Formatted WhatsApp message
    """
    intent = result['response'].intent
    answer = result['response'].answer
    sources = result.get('sources', [])
    
    # Add emoji based on intent
    intent_emojis = {
        'Admission_Dates': '📅',
        'Scholarship': '💰',
        'Fee_Structure': '💵',
        'Hostel': '🏠',
        'Transport': '🚌',
        'Library': '📚',
        'Departments': '🎓',
        'Contact': '📞',
        'Eligibility': '✅',
        'Entry_Test': '📝',
    }
    
    emoji = intent_emojis.get(intent, 'ℹ️')
    
    # Format main response
    formatted = f"{emoji} *{intent.replace('_', ' ')}*\n\n{answer}"
    
    # Add helpful footer
    formatted += "\n\n_Type 'help' for more options_"
    
    return formatted

@app.route('/send-message', methods=['POST'])
def send_message():
    """
    Endpoint to send proactive messages (for admin use)
    """
    data = request.json
    to_number = data.get('to')
    message = data.get('message')
    
    if not to_number or not message:
        return jsonify({"error": "Missing 'to' or 'message'"}), 400
    
    try:
        msg = twilio_client.messages.create(
            body=message,
            from_=f"whatsapp:{os.getenv('TWILIO_PHONE_NUMBER')}",
            to=f"whatsapp:{to_number}"
        )
        return jsonify({"status": "sent", "sid": msg.sid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/analytics', methods=['GET'])
def analytics():
    """Get conversation analytics"""
    stats = logger.get_analytics()
    return jsonify(stats)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f"""
    ╔════════════════════════════════════════════╗
    ║   University FAQ WhatsApp Bot              ║
    ║   Running on http://localhost:{port}        ║
    ╚════════════════════════════════════════════╝
    """)
    app.run(host='0.0.0.0', port=port, debug=True)
