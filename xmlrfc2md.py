import xml.etree.ElementTree as ET
import yaml  # pyyaml package
import sys
import textwrap

wrapper = textwrap.TextWrapper(width=120, replace_whitespace=False, break_on_hyphens=False)

internal_refs = []


def collapse_spaces(t: str):
    lines = t.splitlines()
    out = []
    for ln in lines:
        lst = ln.lstrip()
        if lst != ln:
            lst = " " + lst
        out.append(lst)
    return "\n".join(out)


def extract_text(root: ET):
    output = ""
    for para in root.findall("t"):
        output += para.text + "\n"
    return output


def section_title(elem: ET, level: int):
    anchor_name = elem.get("anchor")
    anchor = ""
    if anchor_name is not None:
        internal_refs.append(anchor_name)
        anchor = "{#" + elem.get("anchor") + "}"
    name = elem.find("name")
    if name is None:
        print("Section with no name")
        return ""
    return "\n" + "#" * level + " " + name.text.strip() + " " + anchor + "\n"


def extract_xref(elem: ET):
    target = elem.get("target")
    section = elem.get("section")
    section_format = elem.get("sectionFormat")

    if target is None:
        print("Missing target in xref")
        return "badxref"
    if target.startswith("RFC"):
        if section_format != "of" and section_format != "comma":
            print("Unsupported xref section format: " + section_format)
            return "badxref"
        if section is None:
            return "{{" + target + "}}"
        else:
            if section_format == "of":
                return "Section " + section + " of {{" + target + "}}"
            else:  # comma
                return "{{" + target + "}}, Section " + section
    return "{{" + target + "}}"


class Lists:
    NoType = 0
    Unordered = 1
    Ordered = 2


def extract_sections(root: ET, level: int, list_type=Lists.NoType) -> str:
    """Extract text from a sequence of <t> elements, possibly nested
"""
    output = ""
    if root.text is not None:
        output += collapse_spaces(root.text)
    for elem in root:
        match elem.tag:
            case "t":
                output += extract_sections(elem, level, )
                output += "\n"
            case "blockquote":
                output += "> " + extract_sections(elem, level)
                output += "\n"
            case "li":
                if list_type == Lists.NoType:
                    pre = ""
                elif list_type == Lists.Unordered:
                    pre = "* "
                else:
                    pre = "1. "
                output += pre + extract_sections(elem, level, )
                output += "\n"
            case "section":
                if elem.get("anchor") != "authors-addresses":
                    # Hack: kdrfc only adds this section if the title is missing
                    output += section_title(elem, level + 1)
                    output += extract_sections(elem, level + 1, )
                    output += "\n"
            case "ul":
                output += extract_sections(elem, level, Lists.Unordered)
            case "ol":
                output += extract_sections(elem, level, Lists.Ordered)
            case "xref":
                output += extract_xref(elem)
            case "bcp14":
                output += elem.text
            case "tt":
                output += "`" + elem.text + "`"
            case "sup":
                output += "<sup>" + elem.text + "</sup>"
            case "contact":
                output += " " + elem.get("fullname")
            case "name" | "references" | "author":
                pass  # section name is processed by section_title(), references processed in extract_preamble(),
                # authors defined twice (?)
            case _:
                print("Skipping unknown element: ", elem.tag)
        if elem.tail is not None:
            output += collapse_spaces(elem.tail)
    return output


def conditional_add(m: dict, key: str, value):
    if value is not None:
        m[key] = value


def extract_preamble(rfc: ET) -> str:
    output = ""
    front = rfc.find("front")
    if front == "":
        sys.exit("No front block found")

    preamble = {}
    title_el = front.find("title")
    title = title_el.text
    conditional_add(preamble, "title", title)
    abbrev = title_el.get("abbrev")
    conditional_add(preamble, "abbrev", abbrev)
    docname = rfc.get("docName")
    conditional_add(preamble, "docname", docname)
    category = rfc.get("category")
    conditional_add(preamble, "category", category)
    ipr = rfc.get("ipr")
    conditional_add(preamble, "ipr", ipr)
    area = front.find("area").text
    conditional_add(preamble, "area", area)
    workgroup = front.find("workgroup").text
    conditional_add(preamble, "workgroup", workgroup)

    keywords = [el.text for el in front.findall("keyword")]
    preamble["keyword"] = keywords

    preamble["stand_alone"] = "yes"  # Magic required for some references to work

    # noinspection PyDictCreation
    pi = {}

    # The following directives are set by default, and may need to be configurable
    pi["rfcstyle"] = "yes"
    pi["strict"] = "yes"
    pi["comments"] = "yes"
    pi["inline"] = "yes"
    pi["text-list-symbols"] = "-o*+"
    pi["docmapping"] = "yes"

    tocinclude = rfc.get("tocInclude")
    if tocinclude == "true":
        pi["toc"] = "yes"
    tocdepth = rfc.get("tocDepth")
    if tocdepth is not None:
        pi["tocindent"] = "yes"  # No direct conversion
    sortrefs = rfc.get("sortRefs")
    if sortrefs == "true":
        pi["sortrefs"] = "yes"
    symrefs = rfc.get("symRefs")
    if symrefs == "true":
        pi["symrefs"] = "yes"

    preamble["pi"] = pi

    authors = convert_authors(front)
    preamble["author"] = authors

    normative = convert_references(rfc, "normative")
    informative = convert_references(rfc, "informative")

    # https://stackoverflow.com/questions/30134110/how-can-i-output-blank-value-in-python-yaml-file
    yaml.SafeDumper.add_representer(
        type(None),
        lambda dumper, value: dumper.represent_scalar(u'tag:yaml.org,2002:null', '')
    )

    output += yaml.safe_dump(preamble, default_flow_style=False)
    output += "\n\n"
    if normative is not None:
        output += yaml.safe_dump({"normative": normative}, default_flow_style=False)
    if informative is not None:
        output += yaml.safe_dump({"informative": informative}, default_flow_style=False)

    return output


def convert_authors(front: ET) -> list[dict]:
    authors = []
    for a in front.findall("author"):
        author = {}
        initials = a.get("initials")
        surname = a.get("surname")
        if initials is not None and surname is not None:
            ins = initials + " " + surname
            author["ins"] = ins
        name = a.get("fullname")
        if name is not None:
            author["name"] = name
        org_el = a.find("organization")
        if org_el is not None:
            org = org_el.text
            if org:
                author["organization"] = org
        uri_el = a.find("uri")
        if uri_el is not None:
            uri = uri_el.text
            author["uri"] = uri
        email_el = a.find("address/email")
        if email_el is not None:
            email = email_el.text
            author["email"] = email

        authors.append(author)
    return authors


def find_references(rfc: ET, ref_type: str) -> ET:
    for block in rfc.findall("./back/references/references"):
        name_el = block.find("./name")
        if name_el is None:
            print("No name for reference block")
            continue
        name = name_el.get("slugifiedName")
        if name == "name-" + ref_type + "-references":
            return block
    return None


def full_ref(ref: ET) -> dict | None:
    out = {}
    target = ref.get("target")
    if target is not None:
        out["target"] = target
    front = ref.find("front")
    if front is None:
        print("Reference with no front")
        return None
    title_el = front.find("title")
    if title_el is None:
        print("Reference with no title")
        return None
    out["title"] = title_el.text
    date_el = front.find("date")
    if date_el is not None:
        month = date_el.get("month")
        year = date_el.get("year")
        if month:
            date = month + " " + year
        else:
            date = year
        out["date"] = date
    authors = convert_authors(front)
    out["author"] = authors
    return out


def convert_references(rfc: ET, ref_type: str) -> dict | None:
    ref_block = find_references(rfc, ref_type)
    if ref_block is None:
        print("No " + ref_type + " references?")
        return None
    ref_list = ref_block.findall("./reference")
    if len(ref_list) == 0:
        print("No " + ref_type + " references?")
        return None
    refs = {}
    for ref in ref_list:
        anchor = ref.get("anchor")
        if anchor is None:
            print("Reference missing an anchor")
            continue
        if (anchor.startswith("RFC") or anchor.startswith("I-D.") or anchor.startswith("BCP") or
                anchor.startswith("STD")):
            refs[anchor] = None
            continue
        target = ref.get("target")
        if target is not None and target.startswith("https://doi.org/"):
            doi = target.removeprefix("https://doi.org/")
            refs[anchor] = "DOI." + doi
            continue
        converted = full_ref(ref)
        if converted is not None:
            refs[anchor] = converted
    return refs


def fill_text(text: str) -> str:
    """https://stackoverflow.com/questions/57081970/python-textwrap-with-n-is-placing-newline-mid-paragraph"""
    paragraphs = text.splitlines()
    text_out = "\n".join([
        wrapper.fill(p) for p in paragraphs
    ])
    return text_out


def parse_rfc(infile: str):
    output = ""
    tree = ET.parse(infile)
    root = tree.getroot()
    if root.tag != "rfc":
        sys.exit("Tag not found:\"rfc\"")

    t = extract_preamble(root)
    output += "---\n"
    output += t
    output += "\n"

    abstract = root.find("front/abstract")
    if abstract == "":
        sys.exit("No abstract found")
    t = extract_text(abstract)
    output += "--- abstract\n\n"
    output += t
    output += "\n\n"

    middle = root.find("middle")
    if middle == "":
        sys.exit("Cannot find middle part of document")
    t = fill_text(extract_sections(middle, 0, False))
    output += "--- middle\n\n"
    output += t

    back = root.find("back")
    if back != "":
        t = fill_text(extract_sections(back, 0, False))
        output += "--- back\n\n"
        output += t

    return output


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: " + sys.argv[0] + " infile outfile")
    infile = sys.argv[1]
    outfile = sys.argv[2]

    markdown = parse_rfc(infile)
    out = open(outfile, "w")
    out.write(markdown)


if __name__ == "__main__":
    main()
