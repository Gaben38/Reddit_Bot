class CommandDontExistException(Exception):
    '''Исключение для случая если команда с заданным именем не существует'''

class CommandExistsException(Exception):
    '''Исключение для случая если команда с заданным именем уже существует'''

class BotDontExistException(Exception):
    '''Исключение для случая если бот с заданным именем не существует'''

class BotExistsException(Exception):
    '''Исключение для случая если бот с заданным именем уже существует'''
	
class BotSectionNotFound(Exception):
    '''Исключение для случая если в praw.ini не найдены данные для бота с заданным именем'''