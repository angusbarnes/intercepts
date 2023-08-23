from parsall.lexing import DefaultLexer
from parsall.core.rule import *

class ElementNameRule(SyntaxRule):

    def match(self, char_stream: CharacterStream) -> str:
        # Check if the first character is a letter or digit
        first_char = char_stream.peek()
        if not first_char.isalnum() and first_char != '(':
            return None
        
        # Start building the identifier
        identifier = char_stream.pop()
        
        # Add any additional letters, underscores, or digits
        while True:
            next_char = char_stream.peek()
            if next_char is None or not ((next_char.isalnum()) or (next_char in'()')):
                break
            identifier += char_stream.pop()
        
        return ("symbol", identifier)

rules = [
    WordRule("UNIT", "ppb", ignore_case=True),
    WordRule("UNIT", "ppt", ignore_case=True),
    WordRule("UNIT", "ppm", ignore_case=True),
    WordRule("UNIT", "g/t", ignore_case=True),
    CharacterRule("UNIT", "%"),
    IgnoreRule(" _-\n\t"),
    ElementNameRule()
    #AlphaNumericRule()
]

lexer = DefaultLexer(rules)

#print(lexer.tokenise("AuR() ppm"))

def TryParse(parse_string: str):
    parsed = []
    try: parsed = lexer.tokenise(parse_string)
    except: return None

    if len(parsed) != 2:
        return None
    
    if parsed[0][0] == 'symbol' and parsed[1][0] == 'UNIT':
        return (parsed[0][1], parsed[1][1])
    
    return None

