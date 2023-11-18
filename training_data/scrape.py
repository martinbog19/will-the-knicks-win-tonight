# Import packages
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
from geopy.distance import geodesic
import calendar
import time
months = [month.lower() for month in calendar.month_name[1:]]


# Define useful functions
def streak(results_list) :

    streak_type, current_res = results_list[0], results_list[0]
    streak = 1
    streaks = [results_list[0]]
    for res in results_list[1:] :
        if res == current_res:
            streak += 1
        else :
            streak = 1
            streak_type = res
        streaks.append(streak * streak_type)
        current_res = res
        
    return [np.nan] + streaks[:-1]

def keep_unique(df) :
    if len(df) == 1 :
        return df
    else :
        return df[df['Tm'] == 'TOT']

# Load and clean the city coordinates data -- add Canadian teams, keep higher population cities
cits, lats, lngs = ['Toronto', 'Vancouver'], [43.6532, 49.2827], [-79.3832, -123.1207] # Canadian cities
cities = pd.read_csv('uscities.csv')[['city', 'lat', 'lng', 'population']]
cities = pd.concat([cities, pd.DataFrame(zip(cits, lats, lngs, [1e9, 1e9]), columns = ['city', 'lat', 'lng', 'population'])]).sort_values('population', ascending = False).reset_index(drop = True)
cities = cities.drop_duplicates(subset = 'city', keep = 'first')

# Create mapping between teams and cities
cityMap = {'Denver Nuggets': 'Denver', 'Detroit Pistons': 'Detroit', 'Indiana Pacers': 'Indianapolis', 'New York Knicks': 'New York',
           'Philadelphia 76ers': 'Philadelphia', 'Phoenix Suns': 'Phoenix', 'Seattle SuperSonics': 'Seattle',
           'Washington Bullets': 'Washington', 'Boston Celtics': 'Boston', 'Golden State Warriors': 'San Francisco',
           'San Antonio Spurs':  'San Antonio', 'New Jersey Nets': 'Brooklyn', 'Atlanta Hawks': 'Atlanta',
           'San Diego Clippers':  'San Diego', 'New Orleans Jazz':  'New Orleans', 'Portland Trail Blazers': 'Portland',
           'Cleveland Cavaliers': 'Cleveland', 'Houston Rockets': 'Houston', 'Kansas City Kings':  'Kansas City',
           'Chicago Bulls': 'Chicago', 'Milwaukee Bucks': 'Milwaukee', 'Los Angeles Lakers':  'Los Angeles',
           'Utah Jazz': 'Salt Lake City', 'Dallas Mavericks': 'Dallas', 'Los Angeles Clippers': 'Los Angeles',
           'Sacramento Kings': 'Sacramento', 'Charlotte Hornets': 'Charlotte', 'Miami Heat': 'Miami', 'Orlando Magic': 'Orlando',
           'Minnesota Timberwolves': 'Minneapolis', 'Toronto Raptors': 'Toronto', 'Vancouver Grizzlies': 'Vancouver',
           'Washington Wizards': 'Washington', 'Memphis Grizzlies': 'Memphis', 'New Orleans Hornets':  'New Orleans',
           'Charlotte Bobcats': 'Charlotte', 'New Orleans/Oklahoma City Hornets': 'Oklahoma City', 
           'Oklahoma City Thunder':  'Oklahoma City', 'Brooklyn Nets': 'Brooklyn', 'New Orleans Pelicans':  'New Orleans'
            }


# Scrape Basketball reference

year = 2021 # Specify year of scrape

print(f'Creating {year-1}-{year} season games data ...')

# Create a dictionary of teams code and number of games played in the season
url = f'https://www.basketball-reference.com/leagues/NBA_{year}_ratings.html'
soup = BeautifulSoup(requests.get(url).content, 'lxml')
soup.find('tr', class_='over_header').decompose()
table = soup.find('table')
teams_dict = pd.read_html(str(table))[0][['Team', 'W', 'L']]
teams_dict['code'] = [x['href'].split('/')[2] for x in table.find_all('a', href = True)]
ngames_dict = dict(zip(teams_dict['code'], teams_dict['W'] + teams_dict['L']))
teams_dict  = dict(zip(teams_dict['Team'], teams_dict['code']))

# Scrape the games of the first month
url = f'https://www.basketball-reference.com/leagues/NBA_{year}_games.html'
soup = BeautifulSoup(requests.get(url).content, 'lxml')
monthly_url = [x['href'] for x in soup.find_all('a', href = True) if x['href'].split('.html')[0].split('-')[-1] in months]
while soup.find('tr', class_ = 'thead') is not None:
    soup.find('tr', class_ = 'thead') .decompose()
games = pd.read_html(str(soup.find('table')))[0]
games['href'] = [x['href'] for x in soup.find('table').find_all('a', href = True) if 'boxscores' in x['href'] and 'html' in x['href']]

# Loop over the other months and concatenate all months together
for m_url in monthly_url[1:]:

    url = 'https://www.basketball-reference.com/' + m_url
    soup = BeautifulSoup(requests.get(url).content, 'lxml')
    m_games = pd.read_html(str(soup.find('table')))[0]
    m_games['href'] = [x['href'] for x in soup.find('table').find_all('a', href = True) if 'boxscores' in x['href'] and 'html' in x['href']]
    games = pd.concat([games, m_games])

# Clean the columns of the games data
games = games.rename(columns = {'Start (ET)':'Time', 'Visitor/Neutral':'Away', 'Home/Neutral':'Home', 'PTS':'PTS_away', 'PTS.1':'PTS_home'})
games['Date'] = games['Date'] + games['Time'].apply(lambda x: ' ' + x[:-1] + x[-1].upper() + 'M')
games['Date'] = pd.to_datetime(games['Date'])
games = games[['Date', 'Home', 'Away', 'href', 'PTS_home', 'PTS_away']]
games = games.sort_values('Date').reset_index(drop = True)
games['Location'] = games['Home'].apply(lambda x: cityMap.get(x))
games['Home'] = games['Home'].apply(lambda x: teams_dict.get(x))
games['Away'] = games['Away'].apply(lambda x: teams_dict.get(x))
games = games.merge(cities.drop(columns = ['population']).rename(columns = {'city': 'Location'}), on = 'Location', how = 'left')

print('Looping over every team ...')
homes, aways = [], []
# Loop over each team
for tm in list(teams_dict.values()) :

    # Clean the columns of the team's games data
    games_tm = games.copy()[(games['Home'] == tm) | (games['Away'] == tm)]
    games_tm['Home?'] = 1 * (games_tm['Home'] == tm)
    games_tm['Opponent'] = (games_tm['Home?'] * games_tm['Away'] + (1 - games_tm['Home?']) * games_tm['Home'])
    games_tm['PTS'] = (games_tm['Home?'] * games_tm['PTS_home'] + (1 - games_tm['Home?']) * games_tm['PTS_away'])
    games_tm['PTS_opp'] = (games_tm['Home?'] * games_tm['PTS_away'] + (1 - games_tm['Home?']) * games_tm['PTS_home'])
    games_tm['W'] = (games_tm['PTS'] > games_tm['PTS_opp']).astype(int)
    games_tm['Team'] = len(games_tm) * [tm]
    games_tm = games_tm.head(ngames_dict.get(tm))
    games_tm = games_tm.sort_values('Date').reset_index(drop = True)
    games_tm['G'] = games_tm.index + 1
    games_tm = games_tm[['Date', 'href', 'Team', 'Opponent', 'G', 'Home?', 'PTS', 'PTS_opp', 'W', 'lat', 'lng']]

    # Create the features -- NRtg, W/L, Streak, Rest, Dist
    features = []
    games_tm['NRtg'] = (games_tm['PTS'] - games_tm['PTS_opp']).rolling(1000, min_periods = 1).mean().shift(1)
    features.append('NRtg')
    for lag in [5, 10, 25] :
        games_tm[f'NRtg_{lag}'] = (games_tm['PTS'] - games_tm['PTS_opp']).rolling(lag, min_periods = 1).mean().shift(1)
        features.append(f'NRtg_{lag}')

    games_tm['W/L'] = games_tm['W'].rolling(1000, min_periods = 1).mean().shift(1)
    features.append('W/L')
    for lag in [5, 10, 25] :
        games_tm[f'W/L_{lag}'] = games_tm['W'].rolling(lag, min_periods = 1).mean().shift(1)
        features.append(f'W/L_{lag}')

    games_tm['Streak'] = streak(games_tm['W'].replace(0, -1))
    features.append('Streak')

    games_tm['Rest'] = (games_tm['Date'] - games_tm['Date'].shift(1)).apply(lambda x: x.total_seconds() / (24 * 3600))
    features.append('Rest')

    coords = [(x, y) for x, y in zip(games_tm['lat'], games_tm['lng'])]
    games_tm['Dist'] = [np.nan] + [geodesic(pt1, pt2).kilometers for pt1, pt2 in zip(coords[:-1], coords[1:])]
    features.append('Dist')

    # Create a subset of the home games
    games_tm_home = games_tm.groupby('Home?').get_group(1)
    for f in ['G', 'W'] + features :
        games_tm_home = games_tm_home.rename(columns = {f : f + '_home'})
    games_tm_home = games_tm_home.rename(columns = {'Team': 'Home', 'Opponent': 'Away', 'PTS': 'PTS_home', 'PTS_opp': 'PTS_away'})

    # Create a subset of the away games
    games_tm_away = games_tm.groupby('Home?').get_group(0)
    for f in ['G', 'W'] + features :
        games_tm_away = games_tm_away.rename(columns = {f : f + '_away'})
    games_tm_away = games_tm_away.rename(columns = {'Team': 'Away', 'Opponent': 'Home', 'PTS': 'PTS_away', 'PTS_opp': 'PTS_home'})

    homes.append(games_tm_home)
    aways.append(games_tm_away)

# Get all home stats and away stats in single DataFrame
homes_df = pd.concat(homes).drop(columns = 'Home?')
aways_df = pd.concat(aways).drop(columns = ['Home?'])
    
# Merge away and home games on the game info
data = homes_df.merge(aways_df, on = ['Date', 'href', 'Home', 'Away', 'PTS_home', 'PTS_away'])
data['PTS_diff'] = data['PTS_home'] - data['PTS_away']
data = data.sort_values('Date').reset_index(drop = True)

# Load the ratings of the players per season
ratings = pd.read_csv('/Users/martinbogaert/Desktop/will-the-knicks-win-tonight/player_ratings.csv')

# Loop over every game
ha_avg_ratings = []
for game_idx, (game_url, home, away) in enumerate(zip(data['href'], data['Home'], data['Away'])) :

    print(f'[{game_idx+1}/{len(data)}] ... Processing {home} vs. {away} ...')

    # Load the boxscore for the looped game
    url = 'https://www.basketball-reference.com/' + game_url
    soup = BeautifulSoup(requests.get(url).content, 'lxml')
    tables = soup.find_all('table')
    ha_avg_rating = []

    # Fetch the number of minutes played by the players -- and merge with the player ratings
    for ha in [home, away] :

        table = tables[np.where([f'{ha}-game-basic' in t.get('id') for t in tables])[0][0]]
        table.find(class_ = 'over_header').decompose()
        while table.find(class_ = 'thead') is not None:
            table.find(class_ = 'thead').decompose()

        boxscore = pd.read_html(str(table))[0][:-1].rename(columns = {'Starters': 'Player'})
        boxscore['MP'] = boxscore['MP'].replace('Did Not Play', '0:00').replace('Did Not Dress', '0:00').replace('Not With Team', '0:00')
        boxscore['MP'] = boxscore['MP'].apply(lambda x: int(x.split(':')[0]) + float(x.split(':')[-1]) / 60 if ':' in x else 0)
        boxscore['ID'] = [x['href'].split('/')[-1].split('.')[0] for x in table.find_all('a', href = True) if 'player' in x['href']]
        boxscore['Year'] = len(boxscore) * [year]
        boxscore = boxscore[['Player', 'ID', 'Year', 'MP']]

        boxscore = boxscore.merge(ratings.drop(columns = ['Player', 'G', 'MP']), on = ['ID', 'Year'])

        ha_avg_rating.append(sum(boxscore['rVORP'] * boxscore['MP']) / sum(boxscore['MP']))
        ha_avg_rating.append(sum(boxscore['rSKILL'] * boxscore['MP']) / sum(boxscore['MP']))

    ha_avg_ratings.append(ha_avg_rating)
    time.sleep(2)

data[['rVORP_home', 'rSKILL_home', 'rVORP_away', 'rSKILL_away']] = ha_avg_ratings
features = features + ['rVORP', 'rSKILL']

for f in features :

    data[f] = data[f'{f}_home'] - data[f'{f}_away']
    data = data.drop(columns = [f'{f}_home', f'{f}_away'])

data.to_csv(f'training_data_{year}.csv', index = None)

# Creates a csv with features and binary target
