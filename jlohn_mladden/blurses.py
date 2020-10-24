import curses
import queue
import threading
import time


FIELD = '''
||_______________________||*|
||,,,,,,,,,,,,,,,,,,,,,,,||*|
||\,,,,,,,,,,,,,,,,,,,,,/||*|
||`\,,,,,,,`[ ]`,,,,,,,/`||*|
||=`\,,,,```/`\```,,,,/`=||*|
||==`\,,```/```\```,,/`==||*|
||===`\,``/`````\``,/`===||*|
||====`\`/```````\`/`====||*|
||=====[ ]``( )``[ ]=====||*|
||======`\```````/`======||*|
||=======`\`````/`=======||*|
||========`\```/`========||*|
||=========`\`/`=========||*|
||==========[ ]==========||*|
||_______________________||*|
'''


FIELD_5 = '''
||_______________________||*|
||,,,,,,,,,,,,,,,,,,,,,,,||*|
||\,,,,,,,,,,,,,,,,,,,,,/||*|
||`\,,,,,,,,,,,,,,,,,,,/`||*|
||=`\,,,`[ ]---[ ]`,,,/`=||*|
||==`\,``/```````\``,/`==||*|
||===`\`|`````````|`/`===||*|
||====`\|`````````|/`====||*|
||=====[ ]``( )``[ ]=====||*|
||======`\```````/`======||*|
||=======`\`````/`=======||*|
||========`\```/`========||*|
||=========`\`/`=========||*|
||==========[ ]==========||*|
||_______________________||*|
'''


SCOREBOARD = '''
B:     A:     
K:     I:     
O:     H:    
'''

class Blurses:

    REFRESH_WAIT_S = 1.0 / 30.0

    def __init__(self):
        self._event_queue = queue.Queue()

    def get_event_queue(self):
        return self._event_queue

    def run(self):
        def _loop(stdscr):
            stdscr.nodelay(True)
            stdscr.clear()

            num_rows, num_cols = stdscr.getmaxyx()

            field = curses.newwin(16, 29, 0, 0)
            lineup = curses.newwin(11, num_cols - 30, 0, 32)
            scoreboard = curses.newwin(3, 14, 12, 32)

            while True:
                keypress = stdscr.getch()
                if keypress == ord('q'):
                    break
                self.render(stdscr, field, lineup, scoreboard)

                time.sleep(self.REFRESH_WAIT_S)

        curses.wrapper(_loop)

    def render(self, stdscr, field, lineup, scoreboard):
        self._render_field(field)
        self._render_scoreboard(scoreboard)

    def _render_field(self, screen):
        screen.addstr(0, 0, FIELD.replace('\n', ''))
        screen.refresh()

    def _render_scoreboard(self, screen):
        screen.addstr(0, 0, SCOREBOARD.replace('\n', ''))
        screen.refresh()


if __name__ == '__main__':
    bluh = Blurses()
    bluh.run()
