"""Transparent topic-based geographic relevance; NOT trader-location data."""
from __future__ import annotations
import re

STATE_NAMES = ['alabama','alaska','arizona','arkansas','california','colorado','connecticut','delaware','florida','georgia','hawaii','idaho','illinois','indiana','iowa','kansas','kentucky','louisiana','maine','maryland','massachusetts','michigan','minnesota','mississippi','missouri','montana','nebraska','nevada','new hampshire','new jersey','new mexico','new york','north carolina','north dakota','ohio','oklahoma','oregon','pennsylvania','rhode island','south carolina','south dakota','tennessee','texas','utah','vermont','virginia','washington','west virginia','wisconsin','wyoming']
CANADA = ['canada','canadian','ontario','quebec','québec','alberta','british columbia','manitoba','saskatchewan','nova scotia','new brunswick','newfoundland','prince edward island','nunavut','yukon','northwest territories','toronto','vancouver','montreal','montréal','ottawa','calgary','edmonton','winnipeg','maple leafs','canadiens','senators','oilers','flames','canucks','jets','blue jays','raptors']
US_TERMS = ['united states','u.s.','usa','american','white house','congress','senate','presidential election','presidential nominee','democrat','republican','federal reserve','fed funds','nonfarm payroll','super bowl','nfl','nba','mlb','ncaa','college football','us open','new york','los angeles','las vegas','chicago','boston','miami','dallas','houston','philadelphia','washington dc','atlanta','seattle','san francisco','knicks','lakers','celtics','warriors','cowboys','yankees','dodgers','mets','red sox','chiefs','eagles']
WORLD_TERMS = ['world cup','champions league','global','worldwide','united nations','europe','european','uk ','britain','british','russia','ukraine','china','india','japan','iran','israel','gaza','bitcoin','ethereum','crypto','oscars','academy awards','grammy','formula 1','f1 ','premier league','world series of','world championship']

def contains(text, phrase):
    return bool(re.search(r'(?<!\w)'+re.escape(phrase)+r'(?!\w)', text))

def regions(row):
    text = (' '.join([str(row.get('title') or ''),str(row.get('category') or ''),
                      str(row.get('slug') or '')])).lower()
    out = set()
    if any(contains(text,phrase) for phrase in CANADA):
        out.add('Canada')
    if any(contains(text,phrase) for phrase in US_TERMS + STATE_NAMES):
        out.add('USA')
    if any(contains(text,phrase) for phrase in WORLD_TERMS):
        out.add('Global')
    # NBA, MLB and NHL markets with Canadian teams can be relevant in both.
    if 'Canada' in out and any(contains(text,s) for s in ['nba','nhl','mlb','raptors','blue jays']):
        out.add('USA')
    # Unclassified themes default to Global and are not silently called U.S.
    return out or {'Global'}

def match_filters(events, region='USA', category='All', search=''):
    result = []
    for r in events:
        if region != 'All' and region not in regions(r):
            continue
        cat = str(r.get('category') or 'other').lower().replace('_','-')
        if category != 'All' and cat != category.lower().replace(' & ','-').replace(' ','-'):
            continue
        if search and search.lower().strip() not in (' '.join([str(r.get('title') or ''),str(r.get('slug') or '')])).lower():
            continue
        result.append(r)
    return result
