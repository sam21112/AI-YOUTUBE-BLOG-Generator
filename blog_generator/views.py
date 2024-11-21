from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.conf import settings
import json
import os
import assemblyai as aai
import openai
from pytube import YouTube, exceptions
from pytube.exceptions import PytubeError, VideoUnavailable
from .models import BlogPost

@login_required
def index(request):
    return render(request, 'index.html')


@csrf_exempt
def generate_blog(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            yt_link = data['link']
        except (KeyError, json.JSONDecodeError):
            return JsonResponse({'error': 'Invalid data sent'}, status=400)

        # Fetch the title
        title = yt_title(yt_link)
        print("Video Title:", title)

        # Get transcription
        transcriptions = get_transcription(yt_link)
        if not transcriptions:
            return JsonResponse({'error': 'Failed to get transcript'}, status=500)

        # Generate blog content
        blog_content = generate_blog_from_transcriptions(transcriptions)
        if not blog_content:
            return JsonResponse({"error": "Failed to generate blog"}, status=500)

        new_blog_article=BlogPost.objects.create(
            user=request.user,
            youtube_title=title,
            youtube_link=yt_link,
            generated_content=blog_content,
        )
        new_blog_article.save()
        return JsonResponse({'content': blog_content})
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)


import requests

def yt_title(yt_link):
    try:
        # Extract video ID from the YouTube URL
        video_id = yt_link.split("v=")[1]
        ampersand_position = video_id.find("&")
        if ampersand_position != -1:
            video_id = video_id[:ampersand_position]
        
        # YouTube Data API v3 URL
        api_key = settings.YOUTUBE_API_KEY
        url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet&id={video_id}&key={api_key}"
        
        # Make the API request
        response = requests.get(url)
        data = response.json()
        
        # Check for errors in response
        if "error" in data:
            print(f"Error fetching video title: {data['error']['message']}")
            return "Error fetching title"
        
        # Return the video title
        title = data["items"][0]["snippet"]["title"]
        return title

    except IndexError:
        print("Invalid YouTube URL format.")
        return "Invalid YouTube URL"
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return "Error fetching title"
    except Exception as e:
        print(f"Unexpected error: {e}")
        return "Unexpected error"



def download_audio(link):
    try:
        yt = YouTube(link)
        print("Received YouTube link:", yt)
        video = yt.streams.filter(only_audio=True).first()
        out_file = video.download(output_path=settings.MEDIA_ROOT)
        base, ext = os.path.splitext(out_file)
        new_file = base + '.mp3'
        os.rename(out_file, new_file)
        return new_file
    except VideoUnavailable:
        print("Video unavailable.")
        return None
    except PytubeError as e:
        print(f"PytubeError during audio download: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error during audio download: {e}")
        return None


def get_transcription(link):
    audio_file = download_audio(link)
    if not audio_file:
        return None

    aai.settings.api_key = settings.ASSEMBLYAI_API_KEY
    transcriber = aai.Transcriber()
    try:
        transcript = transcriber.transcribe(audio_file)
        return transcript.text
    except Exception as e:
        print(f"Error during transcription: {e}")
        return None
 

from openai import OpenAI

client = OpenAI(api_key=settings.OPENAI_API_KEY)

def generate_blog_from_transcriptions(transcription):
    prompt = (
        "Based on the following transcript from a YouTube video, write a comprehensive blog.Do not print anyhting in bold ,italic or anyhting else other thehn normal text. "

        "Do not make it look like a YouTube video; make it look like a proper blog article:\n\n"
        f"{transcription}\n\nArticle:"
    )
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # Use 'gpt-4o' or 'gpt-3.5-turbo' as appropriate
            messages=[
                {"role": "system", "content": "You are an expert content writer."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    
    except openai.APIError as e:
        print(f"OpenAI API Error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected Error: {e}")
        return None
 
def blog_list(request):
            blog_articles=BlogPost.objects.filter(user=request.user)
            return render(request,"all-blogs.html",{'blog_articles':blog_articles})
def blog_details(request,pk):
    blog_article_details=BlogPost.objects.get(id=pk)
    if request.user == blog_article_details.user:
        return render(request,'blog-details.html',{'blog_article_details':blog_article_details})
    else:
        return render('/')
def user_login(request):
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['password']

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('/')
        else:
            error_message = "Invalid username or password"
            return render(request, "login.html", {"error_message": error_message})

    return render(request, 'login.html')


def user_signup(request):
    if request.method == "POST":
        username = request.POST["username"]
        email = request.POST["email"]
        password = request.POST["password"]
        repeat_password = request.POST["repeatPassword"]

        if password == repeat_password:
            try:
                user = User.objects.create_user(username, email, password)
                user.save()
                login(request, user)
                return redirect('/')
            except Exception as e:
                error_message = f"Error creating account: {e}"
                return render(request, 'signup.html', {'error_message': error_message})
        else:
            error_message = 'Passwords do not match'
            return render(request, 'signup.html', {'error_message': error_message})

    return render(request, 'signup.html')


def user_logout(request):
    logout(request)
    return redirect('/')
