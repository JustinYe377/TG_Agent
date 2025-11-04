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
You will see output in your terminal like this: 

```
streamlit run demo.py

  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:xxxxx
  Network URL: http://xxxxxxxxxxxxxxxxxx
```
Copy paste the local URL to your web browser, it should show web ui of TG agent

For Gemini API, copy paste your own API keys to the left top bar
## Example Interactions:
  You: "I'm bored"
> Agent: "Time to get out there! Here's a 2-mile walk through 
> uptown with the Farmers Market (ends in 1 hour!), live music 
> at the coffee shop, and the art fair by the river. GO NOW!"

  You: "Want to walk by the river"
> Agent: "Perfect! I've got a scenic river walk that passes 
> 3 local events happening RIGHT NOW..."

## Current Stages: 
- Default prompt setted
- Both local and Gemini api work in WebUi
- Routing system need to be improved, it can only start from a demo location
- Map features(it can only draw a straghit line from A to B)
- weather and temperature showing

## WebUI
### UI
![UI Screenshot](UI/UI.png)
### Map
![map Screenshot](UI/Routes.png)