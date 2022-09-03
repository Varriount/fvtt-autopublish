# Click uses argv[0] when printing help messages, etc.
import sys
if sys.argv[0] == '__main__.py':
    sys.argv[0] = 'fvtt-autopublish'

from fvtt_autopublish import main

if __name__ == '__main__':
    main()
