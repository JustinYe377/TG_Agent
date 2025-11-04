# TG agent
## System Requirements
Python 3.8 or higher
Ollama running locally
Google Gemini API key
Internet connection for weather data and API calls

## LLM models
For now, TG agent assumed user using local LLM-llama3:latest and Gemini API gemini-2.0-flash-exp
Any unmatched models will not return vaild respone

## How to use
```
# Install dependencies
pip install -r requirements.txt

# Run local LLM
ollama run llama3:latest

# Run the app
streamlit run demo.py
```

## Example Interactions:
  You: "I'm bored"
> Agent: "Time to get out there! Here's a 2-mile walk through 
> uptown with the Farmers Market (ends in 1 hour!), live music 
> at the coffee shop, and the art fair by the river. GO NOW!"

  You: "Want to walk by the river"
> Agent: "Perfect! I've got a scenic river walk that passes 
> 3 local events happening RIGHT NOW..."