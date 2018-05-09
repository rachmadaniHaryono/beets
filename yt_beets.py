#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""simple script for download youtube mp3 and add to beets.

workflow
- search title/artist or both from beets
- search youtube query
- choose and download youtube video
- import to beets

require
- beets
- bs4
- pafy
- pyav
- tqdm
- youtube-dl
- vcr (test)
"""
from __future__ import division, absolute_import, print_function

from urllib.parse import quote_plus, urlparse, parse_qs
import argparse
import os
import shutil

from beets.autotag import mb
from beets.ui import main as beets_main
from tqdm import tqdm
import av
import bs4
import click
import pafy
import requests


def convert2mp3(filename):
    inp = av.open(filename, 'r')
    ff, _ = os.path.splitext(filename)
    output_filename = ff + '.mp3'
    out = av.open(output_filename, 'w')
    ostream = out.add_stream("mp3")
    for frame in inp.decode(audio=0):
        frame.pts = None
        for p in ostream.encode(frame):
            out.mux(p)
    for p in ostream.encode(None):
        out.mux(p)
    out.close()

    return output_filename


def search_youtube(query):
    yt_q_url = 'https://www.youtube.com/results?search_query={}'.format(
        quote_plus(query))
    resp = requests.get(yt_q_url)
    soup = bs4.BeautifulSoup(resp.text, 'html.parser')
    hrefs = list(map(lambda x: x.attrs.get('href', None), soup.select('a')))
    hrefs_with_qs = list(filter(lambda x: urlparse(x).query, hrefs))
    v_parts = list(map(
        lambda x: parse_qs(urlparse(x).query).get('v', [None])[0],
        hrefs_with_qs
    ))
    v_parts = set(list(filter(lambda x: x, v_parts)))
    return v_parts


def print_youtube_tracks(pafy_objs, sort=True, index=True):
    print('youtube tracks:')
    yt_vs = pafy_objs
    if sort:
        yt_vs.sort(key=lambda x: x.title)
    for idx, tr in enumerate(yt_vs, 1):
        m, s = list(map(lambda x: int(x), divmod(tr.length, 60)))
        kwargs = dict(idx=idx, track=tr, minute=m, second=s)
        if index:
            print('[{idx}] {track.title} ({minute}:{second})'.format(**kwargs))
        else:
            print('{track.title} ({minute}:{second})'.format(**kwargs))


def print_mb_tracks(tracks):
    mb_tracks = tracks
    print('Musicbrainz tracks:')
    for idx, tr in enumerate(mb_tracks, 1):
        m, s = list(map(lambda x: int(x), divmod(tr.length, 60)))
        kwargs = dict(idx=idx, track=tr, minute=m, second=s)
        print(
            '[{idx}] {track.artist} - {track.title} ({minute}:{second})'.format(
                **kwargs
            )
        )


def main(args=None):
    """download youtube-dl and import to beets."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", help="musicbrainz title query.", default='')
    parser.add_argument("--artist", help="musicbrainz artis query", default='')
    parser.add_argument(
        "--sort-yt", help="sort youtube tracks", action="store_true")
    parser.add_argument("--query", help="query")
    args = parser.parse_args(args)

    if args.title or args.artist:
        mb_tracks = list(mb.match_track(args.artist, args.title))
        print_mb_tracks(mb_tracks)
    elif args.query:
        mb_tracks = list(mb.match_track('', args.title))
        print_mb_tracks(mb_tracks)
    else:
        mb_tracks = []

    if args.query:
        v_parts = search_youtube(args.query)
        yt_vs = list(map(lambda x: pafy.new(x), v_parts))
        print_youtube_tracks(yt_vs, sort=args.sort_yt)
    else:
        yt_vs = []

    exit_flag = False
    while not exit_flag:
        user_input = input('input>')
        keyword = user_input.split(' ')[0]
        if keyword in ('quit', 'exit', 'q', 'x'):
            exit_flag = True
        elif keyword in ('help', 'h'):
            print(
                """Help:
  (h)elp\t\t\tShow this message.
  (q)uit/e(x)it\t\tExit program.
  download <number>\tDownload youtube.
  search-yt <query>\tRun youtube search.
  search-yt-mb <number>\tRun youtube search from musicbrainz track.
  search-mb\t\tRun musicbrainz search.
  show-yt\t\t\tShow youtube result.
  show-mb\t\t\tShow musicbrainz result."""
            )
        elif keyword == 'download':
            if yt_vs:
                input_val = int(user_input.split(' ')[1])
                sel_yt_v = yt_vs[input_val-1]
                best_audio = sel_yt_v.getbestaudio()
                import_flag = True
                if best_audio and best_audio.extension == 'webm':
                    webm_filename = best_audio.download()
                    try:
                        filename = convert2mp3(webm_filename)
                    except UnicodeEncodeError as e:
                        print('{}: {}'.format(type(e), e))
                        new_webm_filename = webm_filename.encode('ascii', 'replace').decode()
                        print('renaming file to ascii filename:\n{}'.format(new_webm_filename)
                        shutil.copy(webm_filename, new_webm_filename)
                        new_convert_filename = convert2mp3(new_webm_filename)
                        filename = os.path.splitext(webm_filename)[0] + '.mp3'
                        print('moving converted file to {}'.format(filename))
                        shutil.move(new_convert_filename, filename)
                elif best_audio:
                    filename = best_audio.download()
                else:
                    import_flag = False
                if import_flag:
                    beets_main(['import', '-s', filename])
            else:
                print('No youtube videos found.')
        elif keyword == 'search-mb':
            artist_input = input('artist>')
            title_input = input('title>')
            mb_tracks = list(mb.match_track(artist_input, title_input))
            print_mb_tracks(mb_tracks)
        elif keyword == 'search-yt':
            input_val = user_input.split(' ', 1)[1]
            v_parts = search_youtube(input_val)
            yt_vs = []
            for v_part in tqdm(v_parts):
                pafy_obj = pafy.new(v_part)
                print_youtube_tracks([pafy_obj], index=False)
                yt_vs.append(pafy_obj)
            print_youtube_tracks(yt_vs, sort=args.sort_yt)
        elif keyword == 'search-yt-mb':
            if mb_tracks:
                input_val = int(user_input.split(' ')[1])
                track = mb_tracks[input_val-1]
                yt_query = '{track.artist} - {track.title}'.format(track=track)
                print('Search "{}"'.format(yt_query))
                v_parts = search_youtube(yt_query)
                yt_vs = list(map(lambda x: pafy.new(x), v_parts))
                print_youtube_tracks(yt_vs, sort=args.sort_yt)
            else:
                print('No musicbrainz track found.')
        elif keyword == 'show-yt':
            if yt_vs:
                print_youtube_tracks(yt_vs, sort=args.sort_yt)
            else:
                print('No youtube videos found.')
        elif keyword == 'show-mb':
            if mb_tracks:
                print_mb_tracks(mb_tracks)
            else:
                print('No musicbrainz track found.')
        else:
            if keyword != '':
                print('Unknown keyword.')


if __name__ == '__main__':
    main()
