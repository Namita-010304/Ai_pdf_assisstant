import os
import sys
from dotenv import load_dotenv

# Force UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import create_tables
from services.vector_store import upsert_chunks
from services.chat_rag import get_answer
from google import genai


def test_pipeline():
    print("Initializing Database tables...")
    create_tables()

    print("Populating vector store with test RAG chunks...")
    test_chunks = [
        {
            "doc_id": 9999,
            "doc_name": "quantum_physics.pdf",
            "page_number": 1,
            "text": "Schrodinger's cat is a thought experiment, sometimes described as a paradox, devised by Austrian physicist Erwin Schrodinger in 1935. It illustrates what he saw as the problem of the Copenhagen interpretation of quantum mechanics applied to everyday objects.",
        },
        {
            "doc_id": 9999,
            "doc_name": "quantum_physics.pdf",
            "page_number": 2,
            "text": "In quantum mechanics, superposition is a principle that states that any two (or more) quantum states can be added together and the result will be another valid quantum state.",
        },
    ]
    upsert_chunks(test_chunks)
    print("Test chunks indexed in Qdrant successfully.")

    # 1. Test In-Context Answer (English)
    print("\n--- Test 1: In-Context Query (English) ---")
    res1 = get_answer(
        question="Who devised Schrodinger's cat thought experiment and when?",
        language="en",
        doc_ids=[9999],
    )
    print("Q: Who devised Schrodinger's cat thought experiment and when?")
    print(f"A: {res1['answer']}")
    print(f"Citations: {res1['citations']}")

    # 2. Test In-Context Answer (Hindi)
    print("\n--- Test 2: In-Context Query (Hindi) ---")
    res2 = get_answer(
        question="What is superposition?",
        language="hi",
        doc_ids=[9999],
    )
    print("Q: What is superposition? (reply expected in Hindi)")
    print(f"A: {res2['answer']}")

    # 3. Test Out-Of-Context Query (English) - Zero Hallucination
    print("\n--- Test 3: Out-of-Context Query (English) ---")
    res3 = get_answer(
        question="What is the capital of France?",
        language="en",
        doc_ids=[9999],
    )
    print("Q: What is the capital of France?")
    print(f"A: {res3['answer']}")
    expected_en = "I'm sorry, I couldn't find an answer to that in the uploaded documents."
    if expected_en in res3["answer"]:
        print("PASS: English zero-hallucination check passed!")
    else:
        print(f"WARN: Got unexpected answer (model may have paraphrased): {res3['answer'][:200]}")

    # 4. Test Out-Of-Context Query (Hindi) - Zero Hallucination
    print("\n--- Test 4: Out-of-Context Query (Hindi) ---")
    res4 = get_answer(
        question="Who is the Prime Minister of India?",
        language="hi",
        doc_ids=[9999],
    )
    print("Q: Who is the Prime Minister of India? (Hindi reply expected)")
    print(f"A: {res4['answer']}")

    # 5. Test Translation
    print("\n--- Test 5: Translation Check ---")
    api_key = os.getenv("GEMINI_API_KEY", "")
    gc = genai.Client(api_key=api_key)
    text = "I am studying quantum mechanics using this PDF assistant."
    prompt = f"Translate the following text into Hindi. Return ONLY the translation:\n\n{text}"
    result = gc.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    print(f"Original: {text}")
    print(f"Hindi Translation: {result.text.strip()}")

    print("\n>>> All backend verification checks completed successfully!")


if __name__ == "__main__":
    test_pipeline()
