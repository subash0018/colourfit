import {
    PRODUCTS
} from "../data/products.js";


export class Catalogue {


    constructor() {

        this.products = PRODUCTS;

        this.gender = "Men";

        this.level = "All";

        this.category = "All";

        this.search = "";

    }



    setGender(gender) {

        this.gender = gender;

        this.level = "All";

        this.category = "All";

    }



    setLevel(level) {

        this.level = level;

        this.category = "All";

    }



    setCategory(category) {

        this.category = category;

    }



    setSearch(search) {

        this.search =
            search
                .trim()
                .toLowerCase();

    }



    getLevels() {

        const levels =

            this.products

                .filter(
                    product =>
                        product.gender ===
                        this.gender
                )

                .map(
                    product =>
                        product.level
                );


        return [
            "All",
            ...new Set(levels)
        ];

    }



    getCategories() {

        const products =

            this.products.filter(
                product =>

                    product.gender ===
                    this.gender

                    &&

                    (
                        this.level === "All"
                        ||
                        product.level ===
                        this.level
                    )
            );


        return [
            "All",

            ...new Set(

                products.map(
                    product =>
                        product.category
                )

            )
        ];

    }



    getProducts() {

        return this.products.filter(
            product => {


                if (
                    product.gender !==
                    this.gender
                ) {

                    return false;

                }


                if (
                    this.level !== "All"
                    &&
                    product.level !==
                    this.level
                ) {

                    return false;

                }


                if (
                    this.category !== "All"
                    &&
                    product.category !==
                    this.category
                ) {

                    return false;

                }


                if (
                    this.search
                    &&
                    !product.name
                        .toLowerCase()
                        .includes(
                            this.search
                        )
                ) {

                    return false;

                }


                return true;

            }
        );

    }

}
