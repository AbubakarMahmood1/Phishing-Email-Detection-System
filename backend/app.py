from fastapi import FastAPI
from pydantic import BaseModel
import pickle
import re
import numpy as np
from scipy.sparse import hstack
from fastapi.middleware.cors import CORSMiddleware

# Define email input schema
class EmailInput(BaseModel):
    email: str

# Initialize FastAPI app
app = FastAPI(title="Phishing Email Detection API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

print("Loading models and preprocessing components...")

# Define the feature extraction function here - don't rely on pickle for functions
def extract_email_features(emails):
    # Create empty arrays for features
    num_links = np.zeros((len(emails), 1))
    contains_urgent = np.zeros((len(emails), 1))
    contains_money = np.zeros((len(emails), 1))
    contains_suspicious_domains = np.zeros((len(emails), 1))
    email_length = np.zeros((len(emails), 1))
    
    # Define patterns
    url_pattern = re.compile(r'https?://\S+|www\.\S+')
    urgent_pattern = re.compile(r'urgent|immediate|alert|attention|important|verify', re.IGNORECASE)
    money_pattern = re.compile(r'money|cash|dollar|payment|bank|account|transfer|credit', re.IGNORECASE)
    suspicious_domains = re.compile(r'\.xyz|\.info|\.top|\.club|\.online', re.IGNORECASE)
    
    # Extract features
    for i, email in enumerate(emails):
        # Count URLs
        urls = url_pattern.findall(email)
        num_links[i] = len(urls)
        
        # Check for urgent language
        contains_urgent[i] = 1 if urgent_pattern.search(email) else 0
        
        # Check for money-related terms
        contains_money[i] = 1 if money_pattern.search(email) else 0
        
        # Check for suspicious domains
        contains_suspicious_domains[i] = 1 if suspicious_domains.search(email) else 0
        
        # Email length
        email_length[i] = len(email)
    
    # Return all features as a single array
    return np.hstack([num_links, contains_urgent, contains_money, 
                     contains_suspicious_domains, email_length])

# Load the model and vectorizer
try:
    # Try to load from the backend directory first
    try:
        model_path = 'backend/model.pkl'
        vectorizer_path = 'backend/vectorizer.pkl'
        with open(model_path, 'rb') as model_file:
            model = pickle.load(model_file)
        
        with open(vectorizer_path, 'rb') as vectorizer_file:
            vectorizer = pickle.load(vectorizer_file)
        
        print(f"Advanced model loaded successfully from {model_path}")
        use_advanced_model = True
    except FileNotFoundError:
        # If not found in backend directory, try root directory
        model_path = 'model.pkl'
        vectorizer_path = 'vectorizer.pkl'
        with open(model_path, 'rb') as model_file:
            model = pickle.load(model_file)
        
        with open(vectorizer_path, 'rb') as vectorizer_file:
            vectorizer = pickle.load(vectorizer_file)
        
        print(f"Advanced model loaded successfully from {model_path}")
        use_advanced_model = True
except Exception as e:
    print(f"Error loading advanced model: {e}")
    print("Attempting to load default model...")
    
    try:
        # Try in backend directory first
        try:
            default_model_path = 'backend/default_model.pkl'
            with open(default_model_path, 'rb') as model_file:
                model = pickle.load(model_file)
            
            with open('backend/vectorizer.pkl', 'rb') as vectorizer_file:
                vectorizer = pickle.load(vectorizer_file)
            
            print(f"Default model loaded from {default_model_path}")
        except FileNotFoundError:
            # Try in root directory
            with open('default_model.pkl', 'rb') as model_file:
                model = pickle.load(model_file)
            
            with open('vectorizer.pkl', 'rb') as vectorizer_file:
                vectorizer = pickle.load(vectorizer_file)
            
            print("Default model loaded from root directory")
        
        use_advanced_model = False
    except Exception as e:
        print(f"Error loading default model: {e}")
        raise RuntimeError("Failed to load any model. Please train the model first.")

# Check if BERT is available (optional)
try:
    import torch
    from transformers import BertTokenizer, BertForSequenceClassification
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    
    # Try both paths
    bert_model_paths = ['backend/bert_model', 'bert_model']
    
    bert_loaded = False
    for bert_model_path in bert_model_paths:
        # Only try to load BERT if the directory exists
        import os
        if os.path.exists(bert_model_path):
            bert_model = BertForSequenceClassification.from_pretrained(bert_model_path)
            bert_tokenizer = BertTokenizer.from_pretrained(bert_model_path)
            bert_model.to(device)
            use_bert = True
            bert_loaded = True
            print(f"BERT model loaded successfully from {bert_model_path}")
            break
    
    if not bert_loaded:
        use_bert = False
        print("BERT model directories not found, skipping BERT")
except Exception as e:
    use_bert = False
    print(f"BERT model not available: {e}")

# Function to process email for the standard ML model
def process_email(email_text):
    # Vectorize with TF-IDF
    email_vector = vectorizer.transform([email_text])
    
    if use_advanced_model:
        # Extract additional features
        try:
            additional_features = extract_email_features([email_text])
            # Combine features
            combined_features = hstack([email_vector, additional_features])
            return combined_features
        except Exception as e:
            print(f"Error extracting additional features: {e}")
            print("Falling back to TF-IDF features only")
            return email_vector
    else:
        return email_vector

# Define the predict endpoint
@app.post("/predict")
async def predict(email: EmailInput):
    # Vectorize the input email text
    email_text = email.email
    
    try:
        features = process_email(email_text)
        
        # Predict using the trained model
        prediction = model.predict(features)[0]
        prediction_proba = model.predict_proba(features)[0]
        confidence = prediction_proba[1] if prediction == 1 else prediction_proba[0]
        prediction_label = "Phishing Email" if prediction == 1 else "Safe Email"
        
        # Return the prediction result and confidence
        return {
            "prediction": prediction_label,
            "confidence": float(confidence),
            "model_type": "Advanced ML" if use_advanced_model else "Basic ML"
        }
    except Exception as e:
        import traceback
        return {
            "error": f"Prediction failed: {str(e)}",
            "traceback": traceback.format_exc()
        }

# Add BERT endpoint if available
if use_bert:
    @app.post("/predict_bert")
    async def predict_bert(email: EmailInput):
        email_text = email.email
        
        try:
            # Tokenize
            inputs = bert_tokenizer(
                email_text,
                padding='max_length',
                truncation=True,
                max_length=512,
                return_tensors='pt'
            ).to(device)
            
            # Predict
            bert_model.eval()
            with torch.no_grad():
                outputs = bert_model(**inputs)
            
            logits = outputs.logits
            probabilities = torch.softmax(logits, dim=1).cpu().numpy()[0]
            prediction = int(np.argmax(probabilities))
            confidence = float(probabilities[prediction])
            
            prediction_label = "Safe Email" if prediction == 0 else "Phishing Email"
            
            return {
                "prediction": prediction_label,
                "confidence": confidence,
                "model_type": "BERT"
            }
        except Exception as e:
            import traceback
            return {
                "error": f"BERT prediction failed: {str(e)}",
                "traceback": traceback.format_exc()
            }

# Health check endpoint
@app.get("/")
async def root():
    return {
        "status": "online",
        "models_available": {
            "standard_ml": True,
            "advanced_ml": use_advanced_model,
            "bert": use_bert
        }
    }

# Additional endpoints for model information
@app.get("/model_info")
async def model_info():
    model_info = {
        "standard_ml": {
            "type": type(model).__name__,
            "available": True
        },
        "advanced_features": use_advanced_model,
        "bert_available": use_bert
    }
    
    # Add feature importance if available
    if hasattr(model, 'feature_importances_'):
        # Get feature names if possible
        feature_names = []
        try:
            feature_names = vectorizer.get_feature_names_out().tolist()
            # Add names for additional features
            feature_names.extend(['num_links', 'contains_urgent', 'contains_money', 
                               'contains_suspicious_domains', 'email_length'])
        except:
            feature_names = [f"feature_{i}" for i in range(len(model.feature_importances_))]
        
        # Get top 10 features
        importances = model.feature_importances_
        indices = np.argsort(importances)[::-1][:10]
        
        top_features = [{"name": feature_names[i] if i < len(feature_names) else f"feature_{i}", 
                         "importance": float(importances[i])} 
                        for i in indices]
        
        model_info["top_features"] = top_features
    
    return model_info