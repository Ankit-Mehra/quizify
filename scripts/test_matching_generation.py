#!/usr/bin/env python
"""
Test script to verify matching question generation in enhanced/RAG mode.
Run this after deploying changes to test matching with 4-concept aggregation.

Usage:
    python scripts/test_matching_generation.py --api-url <URL> --token <JWT_TOKEN>
    
Example:
    python scripts/test_matching_generation.py --api-url http://localhost:8000 --token "eyJhbGciOiJI..."
"""

import argparse
import httpx
import json
import sys
from datetime import datetime


def test_matching_generation(api_url: str, token: str):
    """Test matching question generation with enhanced mode."""
    
    # Content with multiple distinct concepts for matching
    content = """
    The Solar System consists of the Sun and the astronomical objects gravitationally bound to it.
    
    **Mercury** is the smallest planet and closest to the Sun. It has no atmosphere and extreme 
    temperature variations. A day on Mercury lasts 176 Earth days.
    
    **Venus** is the second planet from the Sun and is often called Earth's twin due to similar 
    size. It has a thick atmosphere of carbon dioxide and sulfuric acid clouds. Venus rotates 
    backwards compared to other planets.
    
    **Earth** is the third planet and the only known planet with life. It has one natural satellite 
    called the Moon. Earth's atmosphere is 78% nitrogen and 21% oxygen.
    
    **Mars** is the fourth planet, known as the Red Planet due to iron oxide on its surface. 
    It has two small moons: Phobos and Deimos. Mars has the largest volcano in the solar system, 
    Olympus Mons.
    
    **Jupiter** is the largest planet in our solar system. It is a gas giant with a famous 
    Great Red Spot storm. Jupiter has at least 95 known moons, including the four Galilean moons.
    
    **Saturn** is known for its prominent ring system made of ice and rock particles. 
    It is the second-largest planet and has 146 known moons, with Titan being the largest.
    
    **Uranus** is an ice giant that rotates on its side. It has a blue-green color due to 
    methane in its atmosphere. Uranus has 27 known moons named after Shakespeare characters.
    
    **Neptune** is the farthest planet from the Sun. It has the strongest winds in the solar 
    system, reaching 2,100 km/h. Neptune has 16 known moons, with Triton being the largest.
    """
    
    # Request for matching questions in enhanced mode
    request_data = {
        "title": f"Solar System Matching Test - {datetime.now().strftime('%H:%M:%S')}",
        "content": content,
        "num_questions": 5,
        "question_type": "matching",  # Force matching only
        "mode": "enhanced"
    }
    
    print("=" * 60)
    print("Testing Matching Question Generation (Enhanced/RAG Mode)")
    print("=" * 60)
    print(f"API URL: {api_url}")
    print("Question Type: matching")
    print("Mode: enhanced")
    print(f"Num Questions: {request_data['num_questions']}")
    print("=" * 60)
    
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{api_url}/api/quiz/generate/text",
                json=request_data,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
            )
            
            print(f"\nStatus Code: {response.status_code}")
            
            if response.status_code == 201 or response.status_code == 200:
                data = response.json()
                print(f"Quiz ID: {data.get('quiz_id')}")
                print(f"Title: {data.get('title')}")
                print(f"Total Questions: {len(data.get('questions', []))}")
                
                # Analyze questions
                questions = data.get('questions', [])
                matching_count = sum(1 for q in questions if q.get('type') == 'matching')
                other_types = {}
                
                for q in questions:
                    qtype = q.get('type', 'unknown')
                    other_types[qtype] = other_types.get(qtype, 0) + 1
                
                print("\nQuestion Type Distribution:")
                for qtype, count in other_types.items():
                    print(f"  - {qtype}: {count}")
                
                print(f"\n{'='*60}")
                print("MATCHING QUESTIONS DETAILS:")
                print("="*60)
                
                for i, q in enumerate(questions):
                    if q.get('type') == 'matching':
                        print(f"\n[Matching Question {i+1}]")
                        print(f"Question: {q.get('question')}")
                        print(f"Left Items: {q.get('left', [])}")
                        print(f"Right Items: {q.get('right', [])}")
                        print(f"Correct Mapping: {q.get('correct_answer', [])}")
                        print(f"Bloom Level: {q.get('bloom_level')}")
                        print(f"Difficulty: {q.get('difficulty')}")
                        print(f"Concept: {q.get('concept_name')}")
                        print(f"Generation Mode: {q.get('generation_mode')}")
                
                # Summary
                print(f"\n{'='*60}")
                print("SUMMARY")
                print("="*60)
                if matching_count > 0:
                    print(f"✅ SUCCESS: Generated {matching_count} matching question(s)")
                else:
                    print("❌ FAILURE: No matching questions generated")
                    print(f"   All questions were: {list(other_types.keys())}")
                
                # Generation stats
                stats = data.get('generation_stats', {})
                if stats:
                    print("\nGeneration Stats:")
                    for key, value in stats.items():
                        print(f"  - {key}: {value}")
                
                return matching_count > 0
                
            else:
                print("\nError Response:")
                print(json.dumps(response.json(), indent=2))
                return False
                
    except Exception as e:
        print(f"\nException: {type(e).__name__}: {e}")
        return False


def test_mixed_mode(api_url: str, token: str):
    """Test mixed question types in enhanced mode."""
    
    content = """
    Machine Learning is a subset of artificial intelligence that enables systems to learn from data.
    
    **Supervised Learning** uses labeled data to train models. Common algorithms include:
    - Linear Regression for predicting continuous values
    - Decision Trees for classification tasks
    - Support Vector Machines for high-dimensional data
    
    **Unsupervised Learning** finds patterns in unlabeled data. Key techniques:
    - K-Means Clustering groups similar data points
    - Principal Component Analysis reduces dimensions
    - Hierarchical Clustering creates dendrograms
    
    **Deep Learning** uses neural networks with multiple layers:
    - Convolutional Neural Networks (CNNs) for image processing
    - Recurrent Neural Networks (RNNs) for sequence data
    - Transformers for natural language processing
    
    **Reinforcement Learning** trains agents through rewards and penalties:
    - Q-Learning for discrete action spaces
    - Policy Gradient methods for continuous actions
    - Actor-Critic combines value and policy methods
    """
    
    request_data = {
        "title": f"ML Mixed Test - {datetime.now().strftime('%H:%M:%S')}",
        "content": content,
        "num_questions": 10,
        "question_type": "mixed",
        "mode": "enhanced"
    }
    
    print("\n" + "=" * 60)
    print("Testing MIXED Question Types (Enhanced/RAG Mode)")
    print("=" * 60)
    
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{api_url}/api/quiz/generate/text",
                json=request_data,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                questions = data.get('questions', [])
                
                type_counts = {}
                for q in questions:
                    qtype = q.get('type', 'unknown')
                    type_counts[qtype] = type_counts.get(qtype, 0) + 1
                
                print(f"\nTotal Questions: {len(questions)}")
                print("Type Distribution:")
                for qtype, count in type_counts.items():
                    print(f"  - {qtype}: {count}")
                
                matching_count = type_counts.get('matching', 0)
                if matching_count > 0:
                    print(f"\n✅ Mixed mode generated {matching_count} matching question(s)")
                else:
                    print("\n⚠️  No matching questions in mixed mode")
                
                return True
            else:
                print(f"\nError: {response.status_code}")
                print(response.json())
                return False
                
    except Exception as e:
        print(f"\nException: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test matching question generation")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--token", required=True, help="JWT token for authentication")
    parser.add_argument("--test", choices=["matching", "mixed", "both"], default="both",
                       help="Which test to run")
    
    args = parser.parse_args()
    
    success = True
    
    if args.test in ["matching", "both"]:
        if not test_matching_generation(args.api_url, args.token):
            success = False
    
    if args.test in ["mixed", "both"]:
        if not test_mixed_mode(args.api_url, args.token):
            success = False
    
    sys.exit(0 if success else 1)
