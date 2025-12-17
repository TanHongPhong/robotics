"""
Simple test script for LLMService with Llama 3.1
"""
from llm_service import LLMService

def test_llm():
    print("Initializing LLM Service...")
    llm = LLMService()
    
    print(f"\nModel: {llm.model}")
    print(f"Host: {llm.host}")
    
    print("\n" + "="*80)
    print("Testing connection...")
    print("="*80)
    
    status = llm.test_connection()
    print(f"\nStatus: {status.get('status')}")
    if status['status'] == 'connected':
        print(f"✅ Connected!")
        print(f"   GPU: {status.get('gpu_status')}")
        print(f"   Model available: {status.get('model_available')}")
    else:
        print(f"❌ Error: {status.get('error')}")
        return
    
    print("\n" + "="*80)
    print("Testing chat with simple query...")
    print("="*80)
    
    inventory = {
        "items": [
            {"cell_id": 1, "product": "Sản phẩm A", "pick": False, "done": False},
            {"cell_id": 2, "product": "Sản phẩm B", "pick": False, "done": False},
            {"cell_id": 3, "product": "", "pick": False, "done": False},
        ]
    }
    
    result = llm.chat_with_context(
        user_message="Chọn ô 1",
        chat_history=[],
        inventory_context=inventory
    )
    
    print(f"\n\nResponse: {result.get('response')}")
    print(f"\nElapsed time: {result.get('elapsed_time'):.2f}s")
    print(f"Tokens: {result.get('tokens_total')} total")
    
    # Try to parse JSON
    import json
    try:
        parsed = json.loads(result.get('response', ''))
        print(f"\n✅ Valid JSON response!")
        print(f"   Action: {parsed.get('action')}")
        print(f"   Reply: {parsed.get('reply')}")
        print(f"   Reasoning: {parsed.get('reasoning')}")
        print(f"   Updates: {parsed.get('updates')}")
    except json.JSONDecodeError as e:
        print(f"\n❌ JSON parse error: {e}")
        print(f"   Raw response: {result.get('response')[:200]}")

if __name__ == "__main__":
    test_llm()
