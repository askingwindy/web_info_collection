"""Task-only proper-name punctuation; quoted source text stays verbatim."""


def unquoted_book_titles(text):
    """Return paired 《…》 outside every nested 「…」 quotation.

    This scanner does not validate punctuation pairing. Existing language
    checks own malformed quotations; here only complete title pairs count.
    """
    quote_depth = 0
    titles = []
    starts = []
    for index, character in enumerate(text):
        if character == '「':
            quote_depth += 1
        elif character == '」':
            quote_depth = max(0, quote_depth - 1)
        elif character == '《':
            starts.append((index, quote_depth))
        elif character == '》' and starts:
            start, opening_quote_depth = starts.pop()
            if opening_quote_depth == quote_depth == 0:
                titles.append(text[start:index + 1])
    return titles


def validate_task_instruction(text):
    """Require task proper names to use 「」 without rewriting quotations."""
    if unquoted_book_titles(text):
        raise ValueError('task_instruction 在「」之外使用了《…》：'
                         '请按需求用「」括起原题名；已引用「原句里的《…》」须原样保留')


def generated_instruction(text):
    """Format newly generated task prose; never rewrite source quotes or raw goals."""
    characters=list(text); depth=0; starts=[]
    for index,char in enumerate(text):
        if char=='「':depth+=1
        elif char=='」':depth=max(0,depth-1)
        elif char=='《':starts.append((index,depth))
        elif char=='》' and starts:
            start,opening=starts.pop()
            if opening==depth==0:characters[start],characters[index]='「','」'
    text=''.join(characters)
    validate_task_instruction(text)
    return text
