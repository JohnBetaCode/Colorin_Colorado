![Colorín Colorado: a photo of a toucan, its coloring page, and the page being colored in with crayons](docs/images/banner.jpg)

# 🖍️ Colorín Colorado

![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-app-FF4B4B?logo=streamlit&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini-image-8E75B2?logo=googlegemini&logoColor=white)
![Docker Compose](https://img.shields.io/badge/Docker-compose%20up-2496ED?logo=docker&logoColor=white)

Turn your own photos into a coloring book for kids.

Upload photos, convert them one by one into black-and-white line art, write a line about what
each page shows, and export a PDF where every coloring page carries the real photo and an info
box. A bird book shows the real bird and where it lives; a book of landmarks shows a small photo
of the place; a family album shows the day the photo was taken.

> *Colorín colorado, este cuento se ha acabado.* The Spanish line that closes a children's story,
> the way [Once Upon a Time](https://github.com/JohnBetaCode/Once_Upon_a_Time) opens one.

![Two pages of a sample book](docs/images/sample-pages.jpg)

## From photo to coloring page

Pick a style (realistic, cartoon, kawaii or mandala) and an age group (3–5, 6–8, 9+, adults). The
photo is always the reference, so the toucan stays a keel-billed toucan and the boy stays the same
boy.

![Photo, realistic and cartoon coloring pages](docs/images/photo-to-page.jpg)

Two more styles, kawaii and mandala, and a level with fine lines for teens and adults:

![Kawaii, mandala and realistic for adults](docs/images/more-styles.jpg)

Whatever the model returns, the page that reaches the PDF is pure black and white: copied colors
are dropped, solid black areas become outlines, lines are thickened for small hands, and a
"photo of a printed page" is cut down to the drawing. See the [spike](docs/spike.md) for what
the model gets wrong and how each case is handled.

Without the AI, a photo can also become a **mystery mosaic**: a faint grid with a symbol in every
cell and a legend that says how to fill each one. Color it in and the picture appears; the
solutions are at the end of the book.

## The workbench

One page at a time: the photo and its caption on the left, the coloring page and its versions on
the right. Crop, convert, regenerate with instructions, approve, next.

![Workbench](docs/images/ui-workbench.png)

## Try it

The [setup guide](docs/setup.md) gets it running with Docker in a few minutes, then open
http://localhost:8502 and create your first book.

## Learn more

- [Features](docs/features.md): everything the app does, and what building it cost.
- [Setup](docs/setup.md): requirements, running, configuration, tests, troubleshooting.
- [User guide](docs/usage.md): a book from start to finish, captions, export options, costs.
- [Architecture](docs/architecture.md): modules, data layout, pipelines, design decisions.
- [Plan](docs/plan.md) and [line-art spike](docs/spike.md).

## Contributing

Bug reports, ideas and pull requests are welcome. [CONTRIBUTING.md](CONTRIBUTING.md) explains how to
set up the project, run the tests and the conventions the code follows.

## License

The code is released under the [MIT License](LICENSE).

The sample photos come from Wikimedia Commons: toucan by Bernard Gagnon (CC0), laughing boy by
Basile Morin (CC BY-SA 4.0), girl with pigeons by Ken Ketch (CC BY 2.0). The images in
`docs/images` made from them keep those licenses, so the ones made from the laughing boy are
CC BY-SA 4.0. The banner was drawn by Gemini from the toucan. The PDF typeface, Andika, is by SIL
under the SIL Open Font License; it is installed in the Docker image, not stored in this repository.
